#!/usr/bin/env python3
"""
Setup Cloudflare R2 static website with custom domain
Auth:
- Preferred: API Token via CLOUDFLARE_KEY (Bearer token with proper scopes)
- Optional: Global API Key via CLOUDFLARE_GLOBAL_API_KEY and CLOUDFLARE_EMAIL
Optional: CLOUDFLARE_ACCOUNT_ID to skip account lookup
For R2 S3 ops: CLOUDFLARE_R2_ACCESS_KEY_ID and CLOUDFLARE_R2_SECRET_ACCESS_KEY
"""

import os
import sys
import json
import requests
from typing import Dict, Any
import subprocess

# Configuration
BUCKET_NAME = "lee-app-nz"  # R2 bucket names can't have dots when using S3 API
CUSTOM_DOMAIN = "lee.app.nz"
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")  # Can be set via env var

class CloudflareR2Setup:
    def __init__(self, api_token: str, account_id: str = None):
        self.api_token = api_token
        self.global_api_key = os.environ.get("CLOUDFLARE_GLOBAL_API_KEY")
        self.global_api_email = os.environ.get("CLOUDFLARE_EMAIL")

        if self.api_token:
            self.headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            self.auth_mode = "token"
        elif self.global_api_key and self.global_api_email:
            self.headers = {
                "X-Auth-Key": self.global_api_key,
                "X-Auth-Email": self.global_api_email,
                "Content-Type": "application/json"
            }
            self.auth_mode = "global"
        else:
            self.headers = {"Content-Type": "application/json"}
            self.auth_mode = "none"
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.account_id = account_id
        
    def get_account_id(self) -> str:
        """Fetch the Cloudflare account ID"""
        if self.account_id:
            print(f"✓ Using provided account ID: {self.account_id}")
            return self.account_id
            
        print("  Attempting to fetch account ID...")
        
        # Verify auth according to mode
        if self.auth_mode == "token":
            verify_response = requests.get(
                f"{self.base_url}/user/tokens/verify",
                headers=self.headers
            )
            if verify_response.status_code != 200:
                print(f"⚠ Token verification failed (status: {verify_response.status_code})")
                try:
                    error_data = verify_response.json()
                    print(f"   Details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Response: {verify_response.text}")
            else:
                print(f"✓ Token verified successfully")
        elif self.auth_mode == "global":
            verify_response = requests.get(
                f"{self.base_url}/user",
                headers=self.headers
            )
            if verify_response.status_code != 200:
                print(f"⚠ Global API Key verification failed (status: {verify_response.status_code})")
                try:
                    error_data = verify_response.json()
                    print(f"   Details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Response: {verify_response.text}")
            else:
                print(f"✓ Global API Key verified successfully")
        
        # Try to get accounts
        response = requests.get(
            f"{self.base_url}/accounts",
            headers=self.headers
        )
        
        if response.status_code != 200:
            print(f"⚠ Cannot fetch account list (status: {response.status_code})")
            try:
                error_data = response.json()
                if "errors" in error_data:
                    for error in error_data["errors"]:
                        print(f"   Error {error.get('code', 'N/A')}: {error.get('message', 'Unknown error')}")
                else:
                    print(f"   Response: {json.dumps(error_data, indent=2)}")
            except:
                print(f"   Response text: {response.text}")
            
            print("\n📝 This is common with API tokens. You need to provide your Account ID manually:")
            print("1. Go to https://dash.cloudflare.com")
            print("2. Select your account")
            print("3. On the right sidebar, copy the 'Account ID'")
            print("4. Run: export CLOUDFLARE_ACCOUNT_ID='your-account-id'")
            print("\nExample: export CLOUDFLARE_ACCOUNT_ID='f76d25b8b86cfa5638f43016510d8f77'")
            print("\nNote: API tokens often can't list accounts but can still access specific accounts.")
            raise Exception("Account ID required. Please set CLOUDFLARE_ACCOUNT_ID environment variable.")
        
        data = response.json()
        
        if not data.get("result"):
            print(f"   API Response: {json.dumps(data, indent=2)}")
            raise Exception("No Cloudflare accounts found in API response")
        
        self.account_id = data["result"][0]["id"]
        print(f"✓ Found account ID: {self.account_id}")
        return self.account_id
    
    def verify_permissions(self) -> bool:
        """Verify the credentials have necessary permissions"""
        if self.auth_mode == "token":
            response = requests.get(
                f"{self.base_url}/user/tokens/verify",
                headers=self.headers
            )
            if response.status_code == 200:
                print(f"✓ API token verified")
                return True
            print(f"⚠ Could not verify token permissions")
            return False
        elif self.auth_mode == "global":
            response = requests.get(
                f"{self.base_url}/user",
                headers=self.headers
            )
            if response.status_code == 200:
                print(f"✓ Global API Key verified")
                return True
            print(f"⚠ Could not verify Global API Key")
            return False
        else:
            print("⚠ No authentication provided")
            return False
    
    def create_bucket(self) -> bool:
        """Create R2 bucket using S3 API if available, otherwise use Cloudflare API"""
        # Try S3 API first if credentials are available
        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        
        if access_key and secret_key:
            print(f"  Using S3-compatible API to create bucket...")
            endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
            
            # Check if aws cli is available
            try:
                # Configure AWS CLI temporarily
                env = os.environ.copy()
                env["AWS_ACCESS_KEY_ID"] = access_key
                env["AWS_SECRET_ACCESS_KEY"] = secret_key
                env["AWS_DEFAULT_REGION"] = "auto"
                
                # Check if bucket exists
                check_cmd = [
                    "aws", "s3api", "head-bucket",
                    "--bucket", BUCKET_NAME,
                    "--endpoint-url", endpoint
                ]
                result = subprocess.run(check_cmd, env=env, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"✓ Bucket '{BUCKET_NAME}' already exists")
                    return True
                
                # Create bucket
                create_cmd = [
                    "aws", "s3api", "create-bucket",
                    "--bucket", BUCKET_NAME,
                    "--endpoint-url", endpoint
                ]
                result = subprocess.run(create_cmd, env=env, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"✓ Created bucket '{BUCKET_NAME}'")
                    return True
                else:
                    print(f"  S3 API failed: {result.stderr}")
                    print("  Falling back to Cloudflare API...")
            except FileNotFoundError:
                print("  AWS CLI not found, trying Cloudflare API...")
        
        # Fallback to Cloudflare API
        response = requests.put(
            f"{self.base_url}/accounts/{self.account_id}/r2/buckets/{BUCKET_NAME}",
            headers=self.headers,
            json={
                "name": BUCKET_NAME
            }
        )
        
        if response.status_code == 409:
            print(f"✓ Bucket '{BUCKET_NAME}' already exists")
            return True
        
        response.raise_for_status()
        print(f"✓ Created bucket '{BUCKET_NAME}'")
        return True
    
    def configure_cors(self) -> bool:
        """Configure CORS for the bucket"""
        # Check if we're using S3 credentials
        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        
        if access_key and secret_key:
            print(f"ℹ️  CORS configuration will be set via Cloudflare dashboard if needed")
            return True
        
        try:
            cors_config = [
                {
                    "allowedOrigins": ["*"],
                    "allowedMethods": ["GET", "HEAD", "POST", "PUT", "DELETE"],
                    "allowedHeaders": ["*"],
                    "exposeHeaders": ["ETag", "Content-Length"],
                    "maxAgeSeconds": 3600
                }
            ]
            
            response = requests.put(
                f"{self.base_url}/accounts/{self.account_id}/r2/buckets/{BUCKET_NAME}/cors",
                headers=self.headers,
                json=cors_config
            )
            
            response.raise_for_status()
            print(f"✓ Configured CORS for bucket '{BUCKET_NAME}'")
            return True
        except requests.exceptions.HTTPError:
            print(f"⚠ Could not configure CORS via API")
            print(f"  CORS can be configured manually if needed")
            return True  # Continue anyway
    
    def enable_public_access(self) -> bool:
        """Enable public access for the bucket (make it a website)"""
        # Check if we have S3 credentials to use instead
        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        
        if access_key and secret_key:
            print(f"ℹ️  Note: Public access configuration requires Cloudflare dashboard or API token with R2 permissions")
            print(f"  Please enable public access manually:")
            print(f"  1. Go to https://dash.cloudflare.com")
            print(f"  2. Navigate to R2 → {BUCKET_NAME}")
            print(f"  3. Go to Settings tab")
            print(f"  4. Under 'Public Access', enable 'Allow public access'")
            print(f"  5. You'll get a public URL like: https://pub-....r2.dev")
            return True
        
        try:
            response = requests.put(
                f"{self.base_url}/accounts/{self.account_id}/r2/buckets/{BUCKET_NAME}/public",
                headers=self.headers,
                json={
                    "enabled": True
                }
            )
            
            if response.status_code == 400:
                # Public access might already be enabled
                print(f"✓ Public access already configured for '{BUCKET_NAME}'")
                return True
                
            response.raise_for_status()
            print(f"✓ Enabled public access for bucket '{BUCKET_NAME}'")
            return True
        except requests.exceptions.HTTPError:
            print(f"⚠ Could not enable public access via API")
            print(f"  Please enable it manually in the Cloudflare dashboard")
            return True  # Continue anyway
    
    def get_zone_id(self, domain: str) -> str:
        """Get the zone ID for the domain"""
        # Extract the root domain (e.g., app.nz from lee.app.nz)
        parts = domain.split('.')
        root_domain = '.'.join(parts[-2:])
        
        response = requests.get(
            f"{self.base_url}/zones",
            headers=self.headers,
            params={"name": root_domain}
        )
        response.raise_for_status()
        data = response.json()
        
        if not data["result"]:
            raise Exception(f"Zone not found for domain {root_domain}. Please ensure the domain is added to Cloudflare.")
        
        zone_id = data["result"][0]["id"]
        print(f"✓ Found zone ID for {root_domain}: {zone_id}")
        return zone_id
    
    def setup_custom_domain(self) -> bool:
        """Map custom domain to R2 bucket"""
        try:
            # First, get the zone ID
            zone_id = self.get_zone_id(CUSTOM_DOMAIN)
            
            # Check if subdomain already exists and delete if it does
            response = requests.get(
                f"{self.base_url}/zones/{zone_id}/dns_records",
                headers=self.headers,
                params={"name": CUSTOM_DOMAIN, "type": "CNAME"}
            )
            response.raise_for_status()
            existing_records = response.json()["result"]
            
            for record in existing_records:
                print(f"  Removing existing DNS record for {CUSTOM_DOMAIN}")
                delete_response = requests.delete(
                    f"{self.base_url}/zones/{zone_id}/dns_records/{record['id']}",
                    headers=self.headers
                )
                delete_response.raise_for_status()
            
            # Create CNAME record pointing to R2 public URL
            r2_public_url = f"{BUCKET_NAME}.{self.account_id}.r2.cloudflarestorage.com"
            
            response = requests.post(
                f"{self.base_url}/zones/{zone_id}/dns_records",
                headers=self.headers,
                json={
                    "type": "CNAME",
                    "name": CUSTOM_DOMAIN.split('.')[0],  # Just the subdomain part
                    "content": r2_public_url,
                    "ttl": 1,  # Auto TTL
                    "proxied": True  # Enable Cloudflare proxy for caching and security
                }
            )
            
            if response.status_code == 409:
                print(f"✓ DNS record for {CUSTOM_DOMAIN} already exists")
                return True
                
            response.raise_for_status()
            print(f"✓ Created DNS record: {CUSTOM_DOMAIN} → {r2_public_url}")
            
            # Set up custom hostname for R2
            response = requests.put(
                f"{self.base_url}/accounts/{self.account_id}/r2/buckets/{BUCKET_NAME}/custom_domains",
                headers=self.headers,
                json={
                    "domain": CUSTOM_DOMAIN
                }
            )
            
            if response.status_code in [200, 409]:
                print(f"✓ Custom domain {CUSTOM_DOMAIN} configured for bucket")
                return True
                
            response.raise_for_status()
            return True
            
        except Exception as e:
            print(f"⚠ Custom domain setup: {str(e)}")
            print("  You may need to manually configure the custom domain in Cloudflare dashboard")
            return False
    
    def upload_index_html(self) -> bool:
        """Upload a default index.html file if it doesn't exist"""
        # Check if we have an existing index.html to upload
        local_index = "./index.html"
        if os.path.exists(local_index):
            print(f"  Found local index.html, uploading...")
            with open(local_index, 'r') as f:
                index_content = f.read()
        else:
            # Use default content
            index_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to lee.app.nz</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }
        h1 {
            margin: 0 0 1rem 0;
            font-size: 3rem;
        }
        p {
            margin: 0;
            font-size: 1.2rem;
            opacity: 0.9;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>lee.app.nz</h1>
        <p>Your Cloudflare R2 static site is working!</p>
    </div>
</body>
</html>"""
        
        # Try S3 API first if credentials are available
        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        
        if access_key and secret_key:
            try:
                # Save content to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(index_content)
                    temp_file = f.name
                
                # Upload using AWS CLI
                env = os.environ.copy()
                env["AWS_ACCESS_KEY_ID"] = access_key
                env["AWS_SECRET_ACCESS_KEY"] = secret_key
                env["AWS_DEFAULT_REGION"] = "auto"
                
                endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
                upload_cmd = [
                    "aws", "s3", "cp", temp_file,
                    f"s3://{BUCKET_NAME}/index.html",
                    "--endpoint-url", endpoint,
                    "--content-type", "text/html"
                ]
                result = subprocess.run(upload_cmd, env=env, capture_output=True, text=True)
                
                # Clean up temp file
                os.unlink(temp_file)
                
                if result.returncode == 0:
                    print(f"✓ Uploaded index.html to bucket")
                    return True
                else:
                    print(f"  S3 upload failed: {result.stderr}")
            except Exception as e:
                print(f"  S3 upload error: {e}")
        
        # No CLI available or S3 credentials missing
        print("ℹ️  Skipping index upload: rclone/aws-cli not available or R2 S3 credentials not set")
        print("  You can upload files using the Cloudflare dashboard or the generated deploy script")
        return False
    
    def create_deploy_script(self):
        """Create a deployment script for syncing files"""
        deploy_script = f"""#!/bin/bash
# Deploy script for {CUSTOM_DOMAIN}
# Auto-generated by setup_cloudflare_static_site.py

# Colors for output
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

echo -e "${{GREEN}}🚀 Deploying to {CUSTOM_DOMAIN}${{NC}}"

# Check if CLOUDFLARE_KEY is set
if [ -z "$CLOUDFLARE_KEY" ]; then
    echo -e "${{RED}}❌ Error: CLOUDFLARE_KEY environment variable not set${{NC}}"
    exit 1
fi

# Get account ID (you may want to hardcode this after first run)
ACCOUNT_ID="{self.account_id}"

# Sync using rclone (preferred method)
if command -v rclone &> /dev/null; then
    echo -e "${{YELLOW}}Using rclone to sync files...${{NC}}"
    
    # Configure rclone if not already configured
    if ! rclone listremotes | grep -q "r2:"; then
        echo "Configuring rclone for R2..."
        rclone config create r2 s3 \\
            provider=Cloudflare \\
            access_key_id=$CLOUDFLARE_R2_ACCESS_KEY_ID \\
            secret_access_key=$CLOUDFLARE_R2_SECRET_ACCESS_KEY \\
            endpoint=https://$ACCOUNT_ID.r2.cloudflarestorage.com \\
            acl=private
    fi
    
    # Sync files
    rclone sync . r2:{BUCKET_NAME}/ \\
        --exclude .git/ \\
        --exclude node_modules/ \\
        --exclude .env \\
        --exclude "*.pyc" \\
        --exclude __pycache__/ \\
        --exclude .DS_Store \\
        --progress
        
# Use AWS CLI as fallback
elif command -v aws &> /dev/null; then
    echo -e "${{YELLOW}}Using AWS CLI to sync files...${{NC}}"
    
    aws s3 sync . s3://{BUCKET_NAME}/ \\
        --endpoint-url https://$ACCOUNT_ID.r2.cloudflarestorage.com \\
        --exclude ".git/*" \\
        --exclude "node_modules/*" \\
        --exclude ".env" \\
        --exclude "*.pyc" \\
        --exclude "__pycache__/*" \\
        --exclude ".DS_Store" \\
        --delete
else
    echo -e "${{RED}}❌ Error: Neither rclone nor aws-cli found${{NC}}"
    echo "Install one of them:"
    echo "  rclone: https://rclone.org/install/"
    echo "  aws-cli: pip install awscli"
    exit 1
fi

echo -e "${{GREEN}}✅ Deployment complete!${{NC}}"
echo -e "View your site at: ${{GREEN}}https://{CUSTOM_DOMAIN}${{NC}}"
"""
        
        with open("deploy-r2.sh", "w") as f:
            f.write(deploy_script)
        
        os.chmod("deploy-r2.sh", 0o755)
        print(f"✓ Created deployment script: deploy-r2.sh")
    
    def run(self):
        """Run the complete setup process"""
        print(f"\n🚀 Setting up Cloudflare R2 static site: {CUSTOM_DOMAIN}\n")
        
        try:
            # Get account ID
            self.get_account_id()
            
            # Create bucket
            self.create_bucket()
            
            # Enable public access
            self.enable_public_access()
            
            # Configure CORS
            self.configure_cors()
            
            # Setup custom domain
            self.setup_custom_domain()
            
            # Upload default index.html
            self.upload_index_html()
            
            # Create deployment script
            self.create_deploy_script()
            
            print(f"\n✅ Setup complete!")
            print(f"\n📝 Next steps:")
            print(f"   1. Your site will be available at: https://{CUSTOM_DOMAIN}")
            print(f"   2. Use ./deploy-r2.sh to sync your files to R2")
            print(f"   3. For rclone, you'll need R2 API tokens (create in Cloudflare dashboard)")
            print(f"\n🔧 Quick deploy commands:")
            print(f"   # With rclone (after setting up R2 API tokens):")
            print(f"   ./deploy-r2.sh")
            print(f"   ")
            print(f"   # With aws-cli:")
            print(f"   aws s3 sync . s3://{BUCKET_NAME}/ --endpoint-url https://{self.account_id}.r2.cloudflarestorage.com")
            
        except requests.exceptions.HTTPError as e:
            print(f"\n❌ API Error: {e}")
            if e.response:
                try:
                    error_data = e.response.json()
                    print(f"   Details: {json.dumps(error_data, indent=2)}")
                    
                    # Check for specific R2 permission error
                    if e.response.status_code == 403 and "r2" in str(e.response.url):
                        print("\n⚠ This looks like a permission issue with R2.")
                        print("\nYour token needs these specific permissions:")
                        print("1. Go to https://dash.cloudflare.com/profile/api-tokens")
                        print("2. Edit your token or create a new one")
                        print("3. Ensure these permissions are set:")
                        print("   - Account → Cloudflare R2:Edit")
                        print("   - Zone → Zone:Read")
                        print("   - Zone → DNS:Edit")
                        print("\nNote: The token must have R2 permissions at the ACCOUNT level, not zone level.")
                except:
                    print(f"   Response: {e.response.text}")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)


def main():
    # Get credentials from environment
    api_token = os.environ.get("CLOUDFLARE_KEY")
    global_api_key = os.environ.get("CLOUDFLARE_GLOBAL_API_KEY")
    global_api_email = os.environ.get("CLOUDFLARE_EMAIL")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")

    if not api_token and not (global_api_key and global_api_email):
        print("❌ Error: Provide authentication via one of the following:")
        print("   - CLOUDFLARE_KEY (API Token) with scopes:")
        print("       Account → Cloudflare R2:Edit; Zone → Zone:Read; Zone → DNS:Edit")
        print("   - OR Global API Key via CLOUDFLARE_GLOBAL_API_KEY and CLOUDFLARE_EMAIL")
        print("\nTo create an API token:")
        print("1. Go to https://dash.cloudflare.com/profile/api-tokens")
        print("2. Click 'Create Token' → 'Custom token'")
        print("3. Set permissions:")
        print("   - Account → Cloudflare R2:Edit")
        print("   - Zone → Zone:Read")
        print("   - Zone → DNS:Edit")
        print("4. Account Resources: Include → Your account")
        print("5. Zone Resources: Include → All zones (or your specific zone)")
        print("6. Export it: export CLOUDFLARE_KEY='your-token-here'")
        sys.exit(1)

    if not account_id:
        print("ℹ️  Tip: You can skip account lookup by setting CLOUDFLARE_ACCOUNT_ID")
        print("   Find it at: https://dash.cloudflare.com → Right sidebar → Account ID")
        print()
    
    # Run setup
    setup = CloudflareR2Setup(api_token, account_id)
    setup.run()


if __name__ == "__main__":
    main()