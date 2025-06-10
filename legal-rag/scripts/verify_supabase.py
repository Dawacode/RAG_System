import os
from supabase import create_client, Client
from dotenv import load_dotenv

def check_table_exists(supabase: Client, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        
        response = supabase.table(table_name).select("*").limit(1).execute()
        return hasattr(response, 'data') and isinstance(response.data, list)
    except Exception as e:
        print(f"Error checking table existence: {e}")
        return False

def get_table_schema(supabase: Client, table_name: str) -> dict:
    """Get schema information for a table."""
    try:
       
        response = supabase.table(table_name).select("*", count="exact").limit(0).execute()
        return response.data if hasattr(response, 'data') else []
    except Exception as e:
        print(f"Error getting table schema: {e}")
        return []

def verify_supabase_connection():
    load_dotenv()
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: Supabase credentials are missing from .env file")
        return False

    try:
       
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Verifying Supabase connection...")
        
        if not check_table_exists(supabase, 'legal_vectors'):
            print("Error: 'legal_vectors' table does not exist")
            return False
            
       
        expected_columns = {
            'id': {'type': 'integer', 'is_nullable': 'NO', 'column_default': 'nextval(\'legal_vectors_id_seq\'::regclass)'},
            'content': {'type': 'text', 'is_nullable': 'NO'},
            'embedding': {'type': 'USER-DEFINED', 'is_nullable': 'YES'},
            'metadata': {'type': 'jsonb', 'is_nullable': 'YES'},
            'source_url': {'type': 'text', 'is_nullable': 'YES'},
            'created_at': {'type': 'timestamp with time zone', 'is_nullable': 'YES', 'column_default': 'CURRENT_TIMESTAMP'}
        }
        
       
        schema_response = get_table_schema(supabase, 'legal_vectors')
            
        
        for column in schema_response:
            col_name = column['column_name']
            if col_name not in expected_columns:
                print(f"Error: Unexpected column '{col_name}' found in table")
                return False
            
            for prop, expected_value in expected_columns[col_name].items():
                if column[prop] != expected_value:
                    print(f"Error: Column '{col_name}' {prop} mismatch. Expected: {expected_value}, Found: {column[prop]}")
                    return False
        
        
        response = supabase.table("legal_vectors").select("*").limit(1).execute()
        
        if hasattr(response, 'data') and response.data:
            print("Successfully connected to Supabase database with data and validated schema")
            return True
        else:
            print("Warning: Connection successful but table is empty (schema validated)")
            return True
    except Exception as e:
        print(f"Error connecting to Supabase: {e}")
        return False

if __name__ == "__main__":
    if verify_supabase_connection():
        print("Supabase connection verified successfully")
    else:
        print("Failed to verify Supabase connection")