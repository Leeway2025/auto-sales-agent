import os
from openai import AzureOpenAI

def main():
    endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
    key=os.getenv('AZURE_OPENAI_API_KEY')
    ver=os.getenv('AZURE_OPENAI_API_VERSION')
    dep=os.getenv('AZURE_OPENAI_DEPLOYMENT')
    print('Endpoint:', endpoint)
    print('API Version:', ver)
    print('Deployment:', dep)
    client=AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version=ver)
    resp=client.chat.completions.create(
        model=dep,
        messages=[
            {"role":"system","content":"You are a health checker."},
            {"role":"user","content":"Reply with OK only."}
        ]
    )
    print('Chat OK:', resp.choices[0].message.content)

if __name__ == '__main__':
    main()

