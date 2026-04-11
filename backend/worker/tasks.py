"""
Main ingestion Celery task.
Steps: Clone → Diff → Walk → Chunk → Embed → Insert → Generate wiki
"""
import logging
import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

from celery import Task
from sqlalchemy.orm import joinedload
from sqlalchemy.dialects.postgresql import insert as pg_insert

import redis as redis_lib

from worker.celery_app import celery_app
from worker.chunker import chunk_file, should_skip_dir, should_skip_file
from worker.embedder import embed_texts
from worker.wiki_generator import generate_architecture_diagram, generate_wiki_page, generate_wiki_structure
from worker.dependency_extractor import extract_dependencies
from rag.retriever import clear_semantic_cache, retrieve_chunks
from db.rls_context import user_rls
from db.session import SessionLocal
from db.models import Repo, Chunk, Job, WikiPage, IndexStatus, JobStatus, WikiGenerationStatus
from core.config import settings
from core.security import decrypt_token

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _release_lock(repo_id: int):
    try:
        _get_redis().delete(f"index_lock:{repo_id}")
    except Exception:
        pass


def _update_job(db, job_id: str, step: str, pct: float, status: JobStatus = JobStatus.running):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.status = status
        job.progress_step = step
        job.progress_pct = pct
        job.updated_at = datetime.utcnow()
        db.commit()


def _update_repo_status(db, repo_id: int, status: IndexStatus, **kwargs):
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if repo:
        repo.index_status = status
        for k, v in kwargs.items():
            setattr(repo, k, v)
        repo.updated_at = datetime.utcnow()
        db.commit()


def _sha_reachable(tmpdir: str, sha: str) -> bool:
    """Check if a commit SHA exists in the local (possibly shallow) clone."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", sha],
            capture_output=True, cwd=tmpdir, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_changed_files(tmpdir: str, old_sha: str) -> List[str] | None:
    """
    Return list of files changed since old_sha.
    Returns None if old_sha is unreachable (shallow clone) or diff fails — caller falls back to full reindex.
    """
    if not _sha_reachable(tmpdir, old_sha):
        return None
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", old_sha, "HEAD"],
            capture_output=True, text=True, cwd=tmpdir, timeout=30,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        pass
    return None


def _safe_error(exc: Exception) -> str:
    """Return a user-facing error string that contains no internal detail."""
    msg = str(exc)
    if "clone" in msg.lower() or "git" in msg.lower():
        return "Repository could not be cloned. Check the URL and your access permissions."
    if "embed" in msg.lower() or "model" in msg.lower():
        return "Embedding failed. The repository may contain files the model cannot process."
    return "Indexing failed. Please try again."


@celery_app.task(bind=True, name="worker.tasks.ingest_repo", max_retries=2, queue="ingest")
def ingest_repo(self: Task, repo_id: int, job_id: str, user_id: int):
    with user_rls(user_id):
        db = SessionLocal()
        tmpdir = None

        try:
            # First DB write as soon as the worker picks up the task — confirms Celery is running
            _update_job(db, job_id, "Starting indexer…", 2)

            repo = db.query(Repo).options(joinedload(Repo.user)).filter(Repo.id == repo_id).first()
            if not repo:
                raise ValueError(f"Repo {repo_id} not found")

            # Decrypt token inside the worker — never pass plaintext tokens as task args
            github_token = decrypt_token(repo.user.github_token_encrypted)

            # ── Step 1: Clone ──────────────────────────────────────────────
            _update_job(db, job_id, "Cloning repository", 5)
            _update_repo_status(db, repo_id, IndexStatus.indexing)

            tmpdir = tempfile.mkdtemp(prefix="rw_clone_")

            # Write token to a temp credential file so it never appears in process listings
            cred_file = tempfile.NamedTemporaryFile(mode="w", suffix=".gitcredentials", delete=False)
            cred_file.write(f"https://x-access-token:{github_token}@github.com\n")
            cred_file.close()
            cred_path = cred_file.name

            try:
                clone_env = {
                    **os.environ,
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "credential.helper",
                    "GIT_CONFIG_VALUE_0": f"store --file={cred_path}",
                }
                result = subprocess.run(
                    ["git", "clone", "--depth=50", "--single-branch",
                     f"https://github.com/{repo.owner}/{repo.name}.git", tmpdir],
                    capture_output=True, text=True, timeout=300, env=clone_env,
                )
            finally:
                try:
                    os.unlink(cred_path)
                except Exception:
                    pass

            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed: {result.stderr[:200]}")

            sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=tmpdir,
            )
            commit_sha = sha_result.stdout.strip()

            # ── Step 2: Determine changed files (diff-based re-index) ─────
            _update_job(db, job_id, "Detecting changes", 12)

            old_sha = repo.last_commit_sha
            is_incremental = False
            changed_file_set: set[str] | None = None

            if old_sha and old_sha != commit_sha:
                changed = _get_changed_files(tmpdir, old_sha)
                if changed is not None:
                    changed_file_set = set(changed)
                    is_incremental = True

            # ── Step 3: Walk files ─────────────────────────────────────────
            _update_job(db, job_id, "Walking files", 18)

            all_files: List[Path] = []
            repo_root = Path(tmpdir)
            for root, dirs, files in os.walk(tmpdir):
                dirs[:] = [d for d in dirs if not should_skip_dir(d)]
                for fname in files:
                    fpath = Path(root) / fname
                    if not should_skip_file(fpath):
                        all_files.append(fpath)

            file_count = len(all_files)
            file_tree = [str(f.relative_to(repo_root)) for f in sorted(all_files)]

            # Extract repo dependencies from manifest files
            dependencies = extract_dependencies(file_tree, tmpdir)

            # For incremental: only process changed files
            if is_incremental and changed_file_set is not None:
                files_to_process = [
                    f for f in all_files
                    if str(f.relative_to(repo_root)) in changed_file_set
                ]
                if not files_to_process:
                    # Nothing to do — jump to finalize
                    _update_repo_status(
                        db, repo_id, IndexStatus.ready,
                        last_commit_sha=commit_sha,
                        indexed_at=datetime.utcnow(),
                        file_count=file_count,
                        file_tree=file_tree,
                        dependencies=dependencies,
                        error_message=None,
                    )
                    _update_job(db, job_id, "Completed (no changes)", 100, JobStatus.completed)
                    return
            else:
                files_to_process = all_files

            # ── Step 4: Chunk files ────────────────────────────────────────
            _update_job(db, job_id, "Chunking files", 30)

            all_chunks = []
            for fpath in files_to_process:
                try:
                    source = fpath.read_text(encoding="utf-8", errors="ignore")
                    source = source.replace("\x00", "")
                    rel_path = str(fpath.relative_to(repo_root))
                    chunks = chunk_file(rel_path, source)
                    all_chunks.extend(chunks)
                except Exception:
                    continue

            # ── Step 5: Embed chunks ───────────────────────────────────────
            # Embeddings are computed BEFORE touching the DB so that if the
            # embedding model fails, no existing data has been deleted yet.
            _update_job(db, job_id, "Embedding chunks", 50)

            chunk_objects = []
            batch_size = settings.embed_batch_size

            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i: i + batch_size]
                texts = [c.content for c in batch]
                try:
                    embeddings = embed_texts(texts, batch_size=batch_size)
                except Exception:
                    if len(batch) == 1:
                        # Single-chunk failure — unrecoverable, let Celery retry the task
                        raise
                    # Batch failure (likely OOM) — fall back to one-at-a-time so
                    # one bad chunk doesn't abort the whole job
                    logger.warning(
                        "Batch embedding failed at offset %d/%d, retrying one-by-one",
                        i, len(all_chunks),
                    )
                    embeddings = []
                    for text in texts:
                        embeddings.append(embed_texts([text], batch_size=1)[0])

                for chunk, emb in zip(batch, embeddings):
                    chunk_objects.append(
                        Chunk(
                            repo_id=repo_id,
                            file_path=chunk.file_path,
                            content=chunk.content,
                            embedding=emb,
                            chunk_type=chunk.chunk_type,
                            name=chunk.name,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            language=chunk.language,
                            chunk_metadata=chunk.metadata,
                        )
                    )

                pct = 50 + (i / max(len(all_chunks), 1)) * 22
                _update_job(db, job_id, f"Embedding chunks ({min(i + batch_size, len(all_chunks))}/{len(all_chunks)})", pct)

            # ── Step 6: Delete old + insert new in one transaction ────────
            # Delete happens AFTER embeddings succeed so a failed embed never
            # leaves the repo with no chunks.
            _update_job(db, job_id, "Inserting chunks into database", 74)

            if is_incremental and changed_file_set:
                changed_paths = list(changed_file_set)
                db.query(Chunk).filter(
                    Chunk.repo_id == repo_id,
                    Chunk.file_path.in_(changed_paths),
                ).delete(synchronize_session=False)
            else:
                db.query(Chunk).filter(Chunk.repo_id == repo_id).delete()
                # Full reindex — invalidate semantic cache so users don't get stale answers
                try:
                    clear_semantic_cache(db, repo_id)
                except Exception:
                    pass

            db.add_all(chunk_objects)
            db.commit()  # single commit: old chunks gone + new chunks visible atomically
            chunk_count = len(chunk_objects)

            # For incremental, total chunk count = existing + new
            if is_incremental:
                total_chunks = db.query(Chunk).filter(Chunk.repo_id == repo_id).count()
            else:
                total_chunks = chunk_count

            # ── Step 7: Clear old wiki pages ──────────────────────────────
            _update_job(db, job_id, "Clearing wiki pages", 80)
            db.query(WikiPage).filter(WikiPage.repo_id == repo_id).delete()
            db.commit()

            # ── Step 8: Generate wiki structure + pre-create all pages ────
            _update_job(db, job_id, "Planning wiki structure", 85)

            top_chunks = [
                {
                    "file_path": c.file_path,
                    "name": c.name,
                    "chunk_type": c.chunk_type,
                    "content": c.content[:200],
                }
                for c in chunk_objects[:30]
            ]

            try:
                mermaid = generate_architecture_diagram(repo.owner, repo.name, file_tree, top_chunks)
            except Exception:
                mermaid = None

            try:
                wiki_structure = generate_wiki_structure(repo.owner, repo.name, file_tree)
            except Exception:
                wiki_structure = [{"id": "overview", "title": "Overview", "parent_id": None, "dir_path": "overview"}]

            _update_job(db, job_id, "Creating wiki pages", 90)

            # Normalize root-like dir_paths and deduplicate
            _ROOT_PATHS = {"", ".", "/", "./"}
            seen_paths: set[str] = set()
            unique_structure = []
            for entry in wiki_structure:
                dp = entry["dir_path"].strip()
                if dp in _ROOT_PATHS:
                    dp = "overview"
                entry = {**entry, "dir_path": dp}
                if dp not in seen_paths:
                    seen_paths.add(dp)
                    unique_structure.append(entry)
            wiki_structure = unique_structure

            # Re-delete wiki pages immediately before inserting — handles any pages
            # that were re-inserted by lingering generate_wiki_page_task jobs from
            # a previous indexing run that executed concurrently with Step 7.
            db.query(WikiPage).filter(WikiPage.repo_id == repo_id).delete()
            db.flush()

            # Create a WikiPage record for every page in the structure using upsert
            # so concurrent tasks can't cause UniqueViolation.
            for entry in wiki_structure:
                path = entry["dir_path"]
                is_overview = path == "overview"
                stmt = pg_insert(WikiPage).values(
                    repo_id=repo_id,
                    path=path,
                    title=entry["title"],
                    content_md=None,
                    mermaid_diagram=mermaid if is_overview else None,
                    generated_at=None,
                    generation_status=WikiGenerationStatus.pending.value,
                ).on_conflict_do_nothing(index_elements=["repo_id", "path"])
                db.execute(stmt)
            db.commit()

            # Dispatch generation tasks for all pages.
            # Overview first so it's ready when the user lands; rest queued after.
            for entry in wiki_structure:
                generate_wiki_page_task.apply_async(
                    args=[repo_id, entry["dir_path"], repo.user_id],
                    queue="wiki",
                )

            # ── Step 9: Finalize ───────────────────────────────────────────
            _update_job(db, job_id, "Finalizing", 98)
            _update_repo_status(
                db, repo_id, IndexStatus.ready,
                last_commit_sha=commit_sha,
                indexed_at=datetime.utcnow(),
                chunk_count=total_chunks,
                file_count=file_count,
                file_tree=file_tree,
                dependencies=dependencies,
                wiki_structure=wiki_structure,
                error_message=None,
            )
            _update_job(db, job_id, "Completed", 100, JobStatus.completed)

        except Exception as exc:
            logger.exception("ingest_repo failed repo_id=%s job_id=%s", repo_id, job_id)
            db.rollback()
            safe_msg = _safe_error(exc)
            _update_repo_status(db, repo_id, IndexStatus.failed, error_message=safe_msg)
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.error = safe_msg
                job.updated_at = datetime.utcnow()
                db.commit()
            raise

        finally:
            _release_lock(repo_id)
            db.close()
            if tmpdir and os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)


@celery_app.task(bind=True, name="worker.tasks.generate_wiki_page_task", max_retries=2, queue="wiki")
def generate_wiki_page_task(self: Task, repo_id: int, path: str, user_id: int):
    """
    Concept-based wiki page generation.
    Uses semantic search (embed the page title) to find the most relevant chunks
    across the entire codebase — not limited to a single directory.
    """
    with user_rls(user_id):
        db = SessionLocal()
        try:
            repo = db.query(Repo).filter(Repo.id == repo_id).first()
            if not repo:
                return

            page = db.query(WikiPage).filter(WikiPage.repo_id == repo_id, WikiPage.path == path).first()
            if not page:
                return

            # Mark as running
            page.generation_status = WikiGenerationStatus.running
            db.commit()

            is_overview = path == "overview"
            page_title = page.title  # semantic title set during ingest (e.g. "Authentication System")

            # Semantic retrieval: find chunks most relevant to this concept title
            # For overview, use a broader query to capture the whole system
            search_query = f"{repo.owner}/{repo.name} {page_title}" if is_overview else page_title
            raw_chunks = retrieve_chunks(db, repo_id, search_query, top_k=40)

            # Strip internal retriever fields
            chunks_data = [
                {
                    "file_path": c["file_path"],
                    "content": c["content"],
                    "name": c.get("name"),
                    "chunk_type": c.get("chunk_type"),
                    "start_line": c.get("start_line"),
                    "end_line": c.get("end_line"),
                    "language": c.get("language"),
                }
                for c in raw_chunks
            ]

            if not chunks_data:
                page.generation_status = WikiGenerationStatus.failed
                db.commit()
                return

            result = generate_wiki_page(
                repo.owner, repo.name, page_title, chunks_data, is_overview=is_overview
            )

            # Re-fetch page in case of concurrent updates
            page = db.query(WikiPage).filter(WikiPage.repo_id == repo_id, WikiPage.path == path).first()
            if page:
                page.title = result["title"]
                page.content_md = result["content_md"]
                if result.get("mermaid_diagram"):
                    page.mermaid_diagram = result["mermaid_diagram"]
                page.generated_at = datetime.utcnow()
                page.generation_status = WikiGenerationStatus.ready
            else:
                db.add(WikiPage(
                    repo_id=repo_id,
                    path=path,
                    title=result["title"],
                    content_md=result["content_md"],
                    mermaid_diagram=result.get("mermaid_diagram"),
                    generated_at=datetime.utcnow(),
                    generation_status=WikiGenerationStatus.ready,
                ))
            db.commit()

        except Exception as exc:
            db.rollback()
            if self.request.retries >= self.max_retries:
                # Exhausted retries — mark failed so frontend doesn't poll forever
                try:
                    page = db.query(WikiPage).filter(WikiPage.repo_id == repo_id, WikiPage.path == path).first()
                    if page:
                        page.generation_status = WikiGenerationStatus.failed
                        db.commit()
                except Exception:
                    pass
                # Clear dispatch key so the next user visit can retry
                try:
                    _get_redis().delete(f"wiki_dispatched:{repo_id}:{path}")
                except Exception:
                    pass
            raise self.retry(exc=exc, countdown=10)
        finally:
            # Clear dispatch key on completion so re-index or manual retry works cleanly
            try:
                _get_redis().delete(f"wiki_dispatched:{repo_id}:{path}")
            except Exception:
                pass
            db.close()
