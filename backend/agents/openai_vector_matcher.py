"""
OpenAI-based Vector Similarity Search for Table and Column Matching
Uses text-embedding-3-small for semantic understanding of schema data
"""
import openai
import numpy as np
import json
import pickle
import os
from typing import List, Dict, Any, Tuple, Optional
import re
from datetime import datetime
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class SchemaItem:
    """Represents a database schema item (table or column)"""
    name: str
    type: str  # 'table' or 'column'
    table_name: str = ""  # For columns, which table they belong to
    data_type: str = ""  # For columns, their data type
    description: str = ""  # Generated description for better embedding
    embedding: Optional[np.ndarray] = None

class OpenAIVectorMatcher:
    def __init__(self, api_key: str = None, cache_dir: str = "backend/storage"):
        # Try environment variable first, then parameter
        self.api_key = os.getenv('OPENAI_API_KEY') or api_key
        if not self.api_key:
            print("⚠️ No OPENAI_API_KEY found in environment variables")
            print("🔄 Vector matching will be unavailable")
        else:
            print("✅ OpenAI API key loaded from environment")
        
        self.cache_dir = cache_dir
        self.embedding_model = "text-embedding-3-small"
        self.embedding_cache_file = os.path.join(cache_dir, "schema_embeddings.pkl")
        self.metadata_cache_file = os.path.join(cache_dir, "schema_metadata.json")
        
        # In-memory storage
        self.schema_items: List[SchemaItem] = []
        self.table_embeddings: Dict[str, np.ndarray] = {}
        self.column_embeddings: Dict[str, np.ndarray] = {}
        
        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)
        
    def _generate_description(self, schema_item: SchemaItem) -> str:
        """Generate descriptive text for better embeddings"""
        if schema_item.type == 'table':
            # Create rich description for table
            name_parts = schema_item.name.replace('_', ' ').replace('-', ' ').split()
            
            # Azure Analytics-specific enhancements
            if 'analytics' in schema_item.name.lower() or 'azure' in schema_item.name.lower():
                desc = f"Azure Analytics data table containing {' '.join(name_parts)}"
                if 'final' in name_parts:
                    desc += " with final processed results"
                if 'output' in name_parts:
                    desc += " containing output data and analytics"
                if 'python' in name_parts:
                    desc += " processed with Python analytics"
            else:
                desc = f"Database table named {' '.join(name_parts)}"
                
            # Add context based on name patterns
            if any(word in name_parts for word in ['refresh', 'update']):
                desc += " with refreshed updated data"
            if any(word in name_parts for word in ['prediction', 'forecast']):
                desc += " containing predictive analytics and forecasts"
            if any(word in name_parts for word in ['feature', 'features']):
                desc += " with feature engineering and data features"
                
            return desc
            
        else:  # column
            # Create rich description for column
            name_parts = schema_item.name.replace('_', ' ').replace('-', ' ').split()
            desc = f"Database column {' '.join(name_parts)}"
            
            if schema_item.data_type:
                desc += f" of type {schema_item.data_type}"
                
            # Add context based on common patterns
            if any(word in name_parts for word in ['id', 'key']):
                desc += " serving as identifier or key"
            elif any(word in name_parts for word in ['date', 'time']):
                desc += " containing date or time information"
            elif any(word in name_parts for word in ['name', 'title']):
                desc += " containing name or title text"
            elif any(word in name_parts for word in ['count', 'number', 'amount']):
                desc += " containing numeric count or amount data"
                
            if schema_item.table_name:
                desc += f" from table {schema_item.table_name}"
                
            return desc
    
    def _get_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Get embeddings from OpenAI API with batching"""
        if not self.api_key:
            print("⚠️ No OpenAI API key available, returning zero embeddings")
            return [np.zeros(1536) for _ in texts]  # text-embedding-3-small is 1536 dims
        
        # Filter and validate inputs
        valid_texts = []
        for text in texts:
            if text and isinstance(text, str) and text.strip():
                valid_texts.append(text.strip())
            else:
                valid_texts.append("empty text")  # Placeholder for invalid inputs
        
        if not valid_texts:
            print("⚠️ No valid texts to embed")
            return [np.zeros(1536) for _ in texts]
            
        # Dynamic batch sizing based on total load
        if len(valid_texts) < 100:
            batch_size = 20  # Small batches for small datasets
        elif len(valid_texts) < 500:
            batch_size = 30
        elif len(valid_texts) < 1000:
            batch_size = 40
        elif len(valid_texts) < 3000:
            batch_size = 50  # Your case: 3000+ items
        else:
            batch_size = 75  # Very large datasets
            
        # For very large datasets, process in chunks with progress tracking
        total_batches = (len(valid_texts) - 1) // batch_size + 1
        print(f"📊 Processing {len(valid_texts)} texts in {total_batches} batches (batch size: {batch_size})")
        
        for i in range(0, len(valid_texts), batch_size):
            batch = valid_texts[i:i + batch_size]
            batch_num = i//batch_size + 1
            print(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} items)")
            
            try:
                # Use OpenAI 1.0+ API format with optimized settings
                from openai import OpenAI
                client = OpenAI(
                    api_key=self.api_key,
                    timeout=180.0,  # Extended timeout for large batches
                    max_retries=3   # More retries for reliability
                )
                
                print(f"🔄 Making OpenAI embeddings API call...")
                print(f"   Model: {self.embedding_model}")
                print(f"   Batch size: {len(batch)}")
                print(f"   Sample text: '{batch[0][:50]}...' " if batch else "No text")
                
                response = client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                
                print(f"✅ OpenAI API call successful")
                batch_embeddings = [np.array(item.embedding) for item in response.data]
                embeddings.extend(batch_embeddings)
                
            except Exception as e:
                print(f"❌ Error getting embeddings: {e}")
                print(f"   Batch size: {len(batch)}")
                print(f"   Sample text: {batch[0][:100] if batch else 'No text'}")
                # Fallback: create zero embeddings
                embeddings.extend([np.zeros(1536) for _ in batch])
                
        return embeddings
    
    def initialize_from_database(self, adapter, force_rebuild: bool = False, max_tables: int = None, 
                                important_tables: List[str] = None):
        """
        Initialize embeddings from database schema with optimization for large schemas
        
        Args:
            adapter: Database adapter
            force_rebuild: Force rebuilding embeddings even if cache exists
            max_tables: Maximum number of tables to embed (None = all)
            important_tables: List of table names to prioritize
        """
        print("🚀 Initializing vector embeddings from database schema...")
        
        # Check if cache exists and is valid
        if not force_rebuild and self._load_cached_embeddings():
            print("✅ Loaded cached embeddings")
            return
            
        # Get all tables
        all_tables = self._get_all_tables(adapter)
        if not all_tables:
            print("⚠️ No tables found")
            return
        
        # Filter and prioritize tables for large schemas
        if len(all_tables) > 50:  # Large schema optimization
            print(f"📊 Large schema detected ({len(all_tables)} tables). Applying optimizations...")
            
            # Prioritize important tables if specified
            if important_tables:
                priority_tables = [t for t in important_tables if t in all_tables]
                remaining_tables = [t for t in all_tables if t not in important_tables]
                tables = priority_tables + remaining_tables
            else:
                # Smart filtering: prioritize tables that look important
                important_patterns = ['main', 'core', 'primary', 'fact', 'dim', 'lookup', 'ref', 'analytics', 'azure']
                priority_tables = []
                other_tables = []
                
                for table in all_tables:
                    if any(pattern in table.lower() for pattern in important_patterns):
                        priority_tables.append(table)
                    else:
                        other_tables.append(table)
                        
                tables = priority_tables + other_tables
            
            # Limit total tables if specified
            if max_tables and len(tables) > max_tables:
                tables = tables[:max_tables]
                print(f"🎯 Limited to {max_tables} most important tables")
        else:
            tables = all_tables
        
        print(f"📊 Processing {len(tables)} tables (from {len(all_tables)} total)")
            
        # Get tables and their schemas
        print("📋 Fetching database schema...")
        tables = self._get_all_tables(adapter)
        
        # Build schema items
        schema_items = []
        
        # Progress tracking for large schemas
        total_estimated_items = len(tables) * 21  # 1 table + ~20 columns per table
        print(f"📊 Estimated {total_estimated_items} schema items to process")
        
        processed_items = 0
        
        # Add table items with parallel column processing for large schemas
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def process_table(table_info):
            """Process a single table and its columns"""
            i, table_name = table_info
            table_items = []
            
            # Create table item
            table_item = SchemaItem(
                name=table_name,
                type='table'
            )
            table_item.description = self._generate_description(table_item)
            table_items.append(table_item)
            
            # Get columns for this table with error handling
            try:
                columns = self._get_table_columns(adapter, table_name)
                print(f"   📋 Table {i+1}/{len(tables)}: {table_name} - {len(columns)} columns")
                
                for col_name, col_type in columns:
                    col_item = SchemaItem(
                        name=col_name,
                        type='column',
                        table_name=table_name,
                        data_type=col_type
                    )
                    col_item.description = self._generate_description(col_item)
                    table_items.append(col_item)
                    
                return table_items, None
                    
            except Exception as e:
                error_msg = f"Error processing columns for {table_name}: {e}"
                return [table_items[0]], error_msg  # Return just the table item
        
        # Process tables - use parallel processing for large schemas
        if len(tables) > 20:
            print(f"🔄 Using parallel processing for {len(tables)} tables...")
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all table processing jobs
                future_to_table = {
                    executor.submit(process_table, (i, table_name)): table_name 
                    for i, table_name in enumerate(tables)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_table):
                    table_name = future_to_table[future]
                    try:
                        table_items, error = future.result()
                        schema_items.extend(table_items)
                        processed_items += len(table_items)
                        
                        if error:
                            print(f"⚠️ {error}")
                            
                    except Exception as e:
                        print(f"⚠️ Failed to process table {table_name}: {e}")
        else:
            # Sequential processing for smaller schemas
            for i, table_name in enumerate(tables):
                table_items, error = process_table((i, table_name))
                schema_items.extend(table_items)
                processed_items += len(table_items)
                
                if error:
                    print(f"⚠️ {error}")
                
                # Progress update every 10 tables
                if (i + 1) % 10 == 0:
                    print(f"📊 Progress: {i+1}/{len(tables)} tables, {processed_items} total items")
        
        print(f"📊 Processing {len(schema_items)} schema items ({len(tables)} tables)")
        
        # Generate embeddings in chunks with incremental caching
        descriptions = [item.description for item in schema_items]
        
        print(f"🔄 Generating embeddings for {len(descriptions)} items...")
        embeddings = self._get_embeddings(descriptions)
        
        # Store embeddings with progress tracking
        print(f"💾 Storing embeddings and building indexes...")
        self.schema_items = []
        for i, (item, embedding) in enumerate(zip(schema_items, embeddings)):
            item.embedding = embedding
            self.schema_items.append(item)
            
            if item.type == 'table':
                self.table_embeddings[item.name] = embedding
            else:
                col_key = f"{item.table_name}.{item.name}"
                self.column_embeddings[col_key] = embedding
            
            # Progress update every 500 items
            if (i + 1) % 500 == 0:
                print(f"   📊 Stored {i+1}/{len(schema_items)} embeddings...")
        
        # Cache the results
        print(f"💾 Saving cache for future use...")
        self._save_cached_embeddings()
        print(f"✅ Vector embeddings initialized: {len(self.table_embeddings)} tables, {len(self.column_embeddings)} columns")
    
    def _get_all_tables(self, adapter) -> List[str]:
        """Get all table names from database"""
        try:
            result = adapter.run("SHOW TABLES")
            if result.error:
                print(f"❌ Error getting tables: {result.error}")
                return []
            return [row[1] for row in result.rows]  # Table name is usually in second column
        except Exception as e:
            print(f"❌ Exception getting tables: {e}")
            return []
    
    def _get_table_columns(self, adapter, table_name: str) -> List[Tuple[str, str]]:
        """Get columns and their types for a table"""
        try:
            # Use DESCRIBE or SHOW COLUMNS depending on database
            result = adapter.run(f'DESCRIBE TABLE "{table_name}"')
            if result.error:
                # Try alternative syntax
                result = adapter.run(f'SHOW COLUMNS FROM "{table_name}"')
                
            if result.error:
                print(f"⚠️ Could not get columns for {table_name}: {result.error}")
                return []
                
            columns = []
            for row in result.rows:
                if len(row) >= 2:
                    col_name = row[0]  # First column is usually name
                    col_type = row[1] if len(row) > 1 else "UNKNOWN"  # Second is type
                    columns.append((col_name, col_type))
            
            return columns  # Keep all columns to preserve data completeness
            
        except Exception as e:
            print(f"⚠️ Exception getting columns for {table_name}: {e}")
            return []
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def find_similar_tables(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict]:
        """Find similar tables using vector similarity"""
        if not self.table_embeddings:
            return []
            
        # Get query embedding
        query_embeddings = self._get_embeddings([query])
        if not query_embeddings:
            return []
            
        query_embedding = query_embeddings[0]
        
        # Calculate similarities
        similarities = []
        for table_name, table_embedding in self.table_embeddings.items():
            similarity = self._cosine_similarity(query_embedding, table_embedding)
            if similarity >= threshold:
                similarities.append({
                    'table_name': table_name,
                    'similarity_score': float(similarity),
                    'match_type': 'vector_semantic',
                    'confidence': self._similarity_to_confidence(similarity)
                })
        
        # Sort by similarity and return top results
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:top_k]
    
    def find_relevant_columns(self, query: str, table_name: str = None, top_k: int = 10) -> List[Dict]:
        """Find relevant columns for a query"""
        if not self.column_embeddings:
            return []
            
        # Get query embedding
        query_embeddings = self._get_embeddings([query])
        if not query_embeddings:
            return []
            
        query_embedding = query_embeddings[0]
        
        # Filter columns by table if specified
        relevant_columns = self.column_embeddings
        if table_name:
            relevant_columns = {k: v for k, v in self.column_embeddings.items() 
                              if k.startswith(f"{table_name}.")}
        
        # Calculate similarities
        similarities = []
        for col_key, col_embedding in relevant_columns.items():
            similarity = self._cosine_similarity(query_embedding, col_embedding)
            table_name_part, col_name = col_key.split('.', 1)
            
            similarities.append({
                'column_name': col_name,
                'table_name': table_name_part,
                'similarity_score': float(similarity),
                'confidence': self._similarity_to_confidence(similarity)
            })
        
        # Sort and return top results
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:top_k]
    
    def hybrid_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Comprehensive search combining tables and columns"""
        # Find similar tables
        similar_tables = self.find_similar_tables(query, top_k)
        
        # Find relevant columns (general)
        relevant_columns = self.find_relevant_columns(query, None, top_k * 2)
        
        # Group columns by table for the top tables
        table_columns = {}
        for table in similar_tables[:3]:  # Top 3 tables
            table_name = table['table_name']
            table_cols = self.find_relevant_columns(query, table_name, 5)
            table_columns[table_name] = table_cols
        
        return {
            'query': query,
            'similar_tables': similar_tables,
            'relevant_columns': relevant_columns,
            'table_specific_columns': table_columns,
            'search_method': 'openai_vector_embeddings'
        }
    
    def _similarity_to_confidence(self, similarity: float) -> float:
        """Convert similarity score to confidence level"""
        # Return the actual similarity score as a float for percentage formatting
        return max(0.0, min(1.0, similarity))  # Clamp between 0 and 1
    
    def _load_cached_embeddings(self) -> bool:
        """Load cached embeddings if they exist"""
        try:
            if not (os.path.exists(self.embedding_cache_file) and 
                   os.path.exists(self.metadata_cache_file)):
                return False
                
            # Load metadata
            with open(self.metadata_cache_file, 'r') as f:
                metadata = json.load(f)
                
            # Check if cache is recent (less than 1 day old)
            cache_time = datetime.fromisoformat(metadata.get('created_at', '2000-01-01'))
            if (datetime.now() - cache_time).days > 1:
                print("🔄 Cache is old, rebuilding...")
                return False
                
            # Load embeddings
            with open(self.embedding_cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                
            self.schema_items = cache_data.get('schema_items', [])
            self.table_embeddings = cache_data.get('table_embeddings', {})
            self.column_embeddings = cache_data.get('column_embeddings', {})
            
            return len(self.table_embeddings) > 0
            
        except Exception as e:
            print(f"⚠️ Error loading cached embeddings: {e}")
            return False
    
    def _save_cached_embeddings(self):
        """Save embeddings to cache"""
        try:
            # Save embeddings
            cache_data = {
                'schema_items': self.schema_items,
                'table_embeddings': self.table_embeddings,
                'column_embeddings': self.column_embeddings
            }
            
            with open(self.embedding_cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
                
            # Save metadata
            metadata = {
                'created_at': datetime.now().isoformat(),
                'model': self.embedding_model,
                'table_count': len(self.table_embeddings),
                'column_count': len(self.column_embeddings)
            }
            
            with open(self.metadata_cache_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            print(f"⚠️ Error saving cached embeddings: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the vector matcher"""
        return {
            "initialized": len(self.table_embeddings) > 0,
            "embedding_model": self.embedding_model,
            "table_count": len(self.table_embeddings),
            "column_count": len(self.column_embeddings),
            "total_schema_items": len(self.schema_items),
            "cache_files_exist": {
                "embeddings": os.path.exists(self.embedding_cache_file),
                "metadata": os.path.exists(self.metadata_cache_file)
            }
        }
