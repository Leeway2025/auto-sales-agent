import requests
import json

try:
    # Try listing all
    print("--- All Agents ---")
    r = requests.get("http://localhost:8000/api/agents")
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except:
        print(r.text)

    # Try listing for demo-user
    print("\n--- Demo User Agents ---")
    r = requests.get("http://localhost:8000/api/agents?user_id=demo-user")
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except:
        print(r.text)

except Exception as e:
    print(e)
