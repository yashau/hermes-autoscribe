#!/usr/bin/env python3
"""
Autoscribe MCP Server
Project-level semantic search for specifications and documentation.

A single MCP server serves multiple repos within a logical project.
Each repo triggers reindex on commit via git pre-commit hook.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib

# FastMCP
from mcp.server.fastmcp import FastMCP

# Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Embeddings
import openai

# Logging
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("autoscribe")


class AutoscribeServer:
    """MCP server for project-level semantic search across multiple repos."""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
        self.project_name = self.config.get("project_name", "default")
        
        # Vector DB path
        self.vector_db_path = config_path.parent / "qdrant_data"
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize Qdrant
        self.qdrant = QdrantClient(path=str(self.vector_db_path))
        self.collection_name = f"{self.project_name}_specs"
        self._ensure_collection()
        
        # Initialize embedding client
        self.embedding_client = self._init_embedding_client()
        
        # MCP server
        self.mcp = FastMCP(f"autoscribe-{self.project_name}")
        self._register_tools()
    
    def _load_config(self) -> dict:
        """Load project configuration."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return {"project_name": "default", "repos": {}}
    
    def _ensure_collection(self):
        """Ensure vector collection exists."""
        collections = self.qdrant.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE)
            )
            logger.info(f"Created collection: {self.collection_name}")
    
    def _init_embedding_client(self) -> openai.OpenAI:
        """Initialize OpenAI-compatible embedding client for Fireworks."""
        api_key = self.config.get("embedding", {}).get("api_key") or os.getenv("FIREWORKS_API_KEY")
        base_url = self.config.get("embedding", {}).get("base_url", "https://api.fireworks.ai/inference/v1")
        
        if not api_key:
            raise ValueError("Fireworks API key required. Set FIREWORKS_API_KEY or in config.")
        
        return openai.OpenAI(api_key=api_key, base_url=base_url)
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Fireworks."""
        model = self.config.get("embedding", {}).get("model", "nomic-ai/nomic-embed-text-v1")
        
        # Nomic expects "search_document:" prefix for documents
        response = self.embedding_client.embeddings.create(
            model=model,
            input=[f"search_document: {text}"]
        )
        return response.data[0].embedding
    
    def _chunk_markdown(self, content: str, file_path: str, repo_name: str) -> List[Dict]:
        """Chunk markdown by headers and return structured chunks."""
        chunks = []
        lines = content.split('\n')
        
        current_section = ""
        current_content = []
        
        for line in lines:
            if line.startswith('#'):
                # Save previous section
                if current_section and current_content:
                    chunks.append({
                        "header": current_section,
                        "content": '\n'.join(current_content),
                        "file_path": file_path,
                        "repo": repo_name
                    })
                # Start new section
                current_section = line.lstrip('#').strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Save final section
        if current_section and current_content:
            chunks.append({
                "header": current_section,
                "content": '\n'.join(current_content),
                "file_path": file_path,
                "repo": repo_name
            })
        
        return chunks
    
    def index_repo(self, repo_name: str, file_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Index specs/docs from a repo. If file_paths is None, reindex all."""
        if repo_name not in self.config.get("repos", {}):
            raise ValueError(f"Unknown repo: {repo_name}")
        
        repo_config = self.config["repos"][repo_name]
        repo_path = Path(repo_config["path"])
        
        indexed = 0
        errors = []
        
        # Determine files to index
        if file_paths:
            # Partial reindex (from git hook)
            files_to_index = [Path(p) for p in file_paths]
            # Delete existing points for these files
            self._delete_files_from_index(repo_name, file_paths)
        else:
            # Full reindex
            files_to_index = []
            for pattern in repo_config.get("include", [".claude/specs/**/*.md", "docs/**/*.md", "README.md"]):
                files_to_index.extend(repo_path.glob(pattern))
            # Delete all existing points for this repo
            self._delete_repo_from_index(repo_name)
        
        # Index files
        for file_path in files_to_index:
            if not file_path.exists():
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8')
                rel_path = str(file_path.relative_to(repo_path))
                
                # Chunk and index
                chunks = self._chunk_markdown(content, rel_path, repo_name)
                
                for i, chunk in enumerate(chunks):
                    embedding = self._get_embedding(f"{chunk['header']}\n{chunk['content']}")
                    
                    point_id = hashlib.md5(
                        f"{repo_name}:{chunk['file_path']}:{i}".encode()
                    ).hexdigest()
                    
                    self.qdrant.upsert(
                        collection_name=self.collection_name,
                        points=[PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "repo": repo_name,
                                "file_path": chunk["file_path"],
                                "header": chunk["header"],
                                "content": chunk["content"],
                                "full_path": str(file_path)
                            }
                        )]
                    )
                    indexed += 1
                
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")
                logger.error(f"Failed to index {file_path}: {e}")
        
        logger.info(f"Indexed {indexed} chunks from {repo_name}")
        return {"indexed": indexed, "errors": errors}
    
    def _delete_files_from_index(self, repo_name: str, file_paths: List[str]):
        """Delete existing points for specific files (for partial reindex)."""
        for file_path in file_paths:
            # Delete all points matching this repo and file
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "repo", "match": {"value": repo_name}},
                            {"key": "file_path", "match": {"value": file_path}}
                        ]
                    }
                }
            )
    
    def _delete_repo_from_index(self, repo_name: str):
        """Delete all points for a repo (for full reindex)."""
        self.qdrant.delete(
            collection_name=self.collection_name,
            points_selector={
                "filter": {
                    "must": [
                        {"key": "repo", "match": {"value": repo_name}}
                    ]
                }
            }
        )
    
    def _register_tools(self):
        """Register MCP tools."""
        
        @self.mcp.tool()
        def search_specs(query: str, repo: Optional[str] = None, top_k: int = 5) -> str:
            """
            Search specifications and documentation across repos in the project.
            
            Args:
                query: The search query (semantic search)
                repo: Optional repo name to limit search. If not provided, searches all repos.
                top_k: Number of results to return (default: 5)
            """
            try:
                # Get query embedding
                model = self.config.get("embedding", {}).get("model", "nomic-ai/nomic-embed-text-v1")
                response = self.embedding_client.embeddings.create(
                    model=model,
                    input=[f"search_query: {query}"]
                )
                query_embedding = response.data[0].embedding
                
                # Build filter
                query_filter = None
                if repo:
                    query_filter = {
                        "must": [
                            {"key": "repo", "match": {"value": repo}}
                        ]
                    }
                
                # Search
                results = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    limit=top_k,
                    query_filter=query_filter
                )
                
                # Format results
                formatted = []
                for r in results:
                    formatted.append({
                        "repo": r.payload["repo"],
                        "file": r.payload["file_path"],
                        "header": r.payload["header"],
                        "content": r.payload["content"][:500] + "..." if len(r.payload["content"]) > 500 else r.payload["content"],
                        "score": r.score
                    })
                
                return json.dumps({
                    "query": query,
                    "repo_filter": repo,
                    "results": formatted,
                    "count": len(formatted)
                }, indent=2)
                
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp.tool()
        def get_spec(feature_name: str, repo: Optional[str] = None) -> str:
            """
            Get a specific spec by feature name (exact filename match without .md).
            
            Args:
                feature_name: The spec name (e.g., "payment-gateway" for "payment-gateway.md")
                repo: Optional repo to limit search
            """
            try:
                # Search for exact filename match
                target_file = f"{feature_name}.md"
                
                # Build filter
                query_filter = {
                    "must": [
                        {"key": "file_path", "match": {"value": target_file}}
                    ]
                }
                if repo:
                    query_filter["must"].append({"key": "repo", "match": {"value": repo}})
                
                # Get all chunks for this file
                results = self.qdrant.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=query_filter,
                    limit=100
                )[0]
                
                if not results:
                    return json.dumps({
                        "error": f"Spec not found: {feature_name}",
                        "searched_file": target_file,
                        "repo_filter": repo
                    })
                
                # Combine chunks
                content_parts = []
                for r in results:
                    header = r.payload.get("header", "")
                    content = r.payload.get("content", "")
                    if header:
                        content_parts.append(f"# {header}\n{content}")
                    else:
                        content_parts.append(content)
                
                return json.dumps({
                    "feature": feature_name,
                    "repo": results[0].payload["repo"],
                    "file": results[0].payload["file_path"],
                    "content": "\n\n".join(content_parts)
                }, indent=2)
                
            except Exception as e:
                logger.error(f"Get spec failed: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp.tool()
        def list_specs(repo: Optional[str] = None) -> str:
            """
            List all specs in the project, optionally filtered by repo.
            
            Args:
                repo: Optional repo name to filter by
            """
            try:
                # Scroll all points
                query_filter = None
                if repo:
                    query_filter = {
                        "must": [
                            {"key": "repo", "match": {"value": repo}}
                        ]
                    }
                
                results = self.qdrant.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=query_filter,
                    limit=1000
                )[0]
                
                # Group by file
                specs = {}
                for r in results:
                    key = (r.payload["repo"], r.payload["file_path"])
                    if key not in specs:
                        specs[key] = {
                            "repo": r.payload["repo"],
                            "file": r.payload["file_path"],
                            "headers": []
                        }
                    if r.payload.get("header"):
                        specs[key]["headers"].append(r.payload["header"])
                
                return json.dumps({
                    "repo_filter": repo,
                    "specs": list(specs.values()),
                    "count": len(specs)
                }, indent=2)
                
            except Exception as e:
                logger.error(f"List specs failed: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp.tool()
        def trigger_reindex(repo: Optional[str] = None) -> str:
            """
            Manually trigger reindex of a repo or all repos.
            
            Args:
                repo: Optional repo name to reindex. If not provided, reindexes all repos.
            """
            try:
                if repo:
                    result = self.index_repo(repo)
                    return json.dumps({"repo": repo, **result})
                else:
                    results = {}
                    for repo_name in self.config.get("repos", {}).keys():
                        results[repo_name] = self.index_repo(repo_name)
                    return json.dumps(results, indent=2)
                    
            except Exception as e:
                logger.error(f"Reindex failed: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp.tool()
        def status() -> str:
            """Get indexing status for all repos in the project."""
            try:
                # Get collection info
                collection_info = self.qdrant.get_collection(self.collection_name)
                
                # Get repo stats
                repo_stats = {}
                for repo_name in self.config.get("repos", {}).keys():
                    count = self.qdrant.count(
                        collection_name=self.collection_name,
                        count_filter={
                            "must": [
                                {"key": "repo", "match": {"value": repo_name}}
                            ]
                        }
                    ).count
                    repo_stats[repo_name] = count
                
                return json.dumps({
                    "project": self.project_name,
                    "collection": self.collection_name,
                    "total_vectors": collection_info.points_count,
                    "repos": repo_stats
                }, indent=2)
                
            except Exception as e:
                logger.error(f"Status failed: {e}")
                return json.dumps({"error": str(e)})
    
    def run(self, transport: str = "stdio"):
        """Run the MCP server."""
        logger.info(f"Starting context-bridge server for project: {self.project_name}")
        logger.info(f"Transport: {transport}")
        self.mcp.run(transport=transport)


def main():
    parser = argparse.ArgumentParser(description="Autoscribe MCP Server")
    parser.add_argument("--config", required=True, help="Path to autoscribe config.json")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport")
    args = parser.parse_args()
    
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    
    server = AutoscribeServer(config_path)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
