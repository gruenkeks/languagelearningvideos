import sys
import google.oauth2.credentials
import google_auth_oauthlib.flow

CLIENT_SECRETS_FILE = "server_scripts/client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    if len(sys.argv) < 2:
        print("Please provide the language you are authenticating for.")
        print("Usage: python3 server_scripts/local_auth.py [Language]")
        print("Example: python3 server_scripts/local_auth.py German")
        sys.exit(1)
        
    language = sys.argv[1]
    token_file = f"server_scripts/youtube_oauth_token_{language}.json"

    print(f"\n--- Logging into YouTube for the {language} channel ---")
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_file, 'w') as f:
        f.write(creds.to_json())
    print(f"\n✅ Token successfully saved to {token_file}!")

if __name__ == "__main__":
    main()