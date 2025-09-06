import requests
import json

def test_enhanced_traditional_query():
    print("🚀 Testing ENHANCED traditional /query endpoint with Pinecone vector search...\n")
    
    # Test the query that was failing before
    query = "What are the recommended messages for NBA marketing actions?"
    
    url = "http://localhost:8000/query"
    payload = {
        "natural_language": query,
        "job_id": "test_enhanced_traditional",
        "db_type": "snowflake"
    }
    
    print(f"📡 Sending query: {query}")
    print(f"🔗 URL: {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"🌐 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ SUCCESS! Enhanced traditional query endpoint working")
            print(f"📊 Response keys: {list(result.keys())}")
            
            # Check SQL
            sql = result.get('sql', 'No SQL found')
            print(f"\n🔧 Generated SQL:")
            print("-" * 60)
            print(sql)
            print("-" * 60)
            
            # Analyze the SQL for correct column usage
            if "Recommended_Msg_Overall" in sql:
                print(f"🎯 PERFECT: SQL contains correct column 'Recommended_Msg_Overall'!")
                print(f"✅ FIXED: Traditional endpoint now uses Pinecone vector search!")
            elif "recommended_message" in sql.lower():
                print(f"❌ STILL BROKEN: SQL contains invalid column 'recommended_message'")
            elif "Final_NBA_Output" in sql:
                print(f"🎯 GOOD: SQL targets correct NBA table family")
                if "Recommended_Msg_Overall" not in sql:
                    print(f"⚠️ PARTIAL: Correct table but might be missing target column")
            elif "SELECT NULL" in sql or "information_schema" in sql:
                print(f"❌ FALLBACK: Using fallback SQL - Pinecone search failed")
            else:
                print(f"❓ UNCLEAR: SQL doesn't contain expected patterns")
                print(f"   Looking for 'recommend' in SQL: {'recommend' in sql.lower()}")
                print(f"   Looking for 'nba' in SQL: {'nba' in sql.lower()}")
            
            # Check execution results
            rows = result.get('rows', [])
            if rows:
                print(f"\n📈 Query returned {len(rows)} rows")
                if rows:
                    print(f"🔍 Sample columns: {list(rows[0].keys()) if isinstance(rows[0], dict) else 'Raw data'}")
                    print(f"🔍 First few rows:")
                    for i, row in enumerate(rows[:3]):
                        print(f"   Row {i+1}: {row}")
                        
                    # Check if we got the target column in results
                    if rows and isinstance(rows[0], dict):
                        if 'Recommended_Msg_Overall' in rows[0]:
                            print(f"🎯 PERFECT: Results contain target column 'Recommended_Msg_Overall'!")
                        else:
                            print(f"📋 Available result columns: {list(rows[0].keys())}")
            else:
                print(f"\n📈 No data rows returned")
                
            # Check Plotly specification
            plotly_spec = result.get('plotly_spec', {})
            if plotly_spec:
                print(f"\n📊 Plotly spec available: {bool(plotly_spec)}")
                print(f"📊 Plotly keys: {list(plotly_spec.keys())}")
            else:
                print(f"\n📊 No Plotly specification provided")
                
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Error: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_enhanced_traditional_query()
