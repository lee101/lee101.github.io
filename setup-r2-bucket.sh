#!/bin/bash
# Setup script for R2 bucket with custom domain
# This script creates and configures the R2 bucket for lee.app.nz

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Setting up R2 bucket for lee.app.nz${NC}"

# Use existing environment variables
R2_ACCESS_KEY_ID=${CLOUDFLARE_R2_ACCESS_KEY_ID:-$R2_ACCESS_KEY_ID}
R2_SECRET_ACCESS_KEY=${CLOUDFLARE_R2_SECRET_ACCESS_KEY:-$R2_SECRET_ACCESS_KEY}
CLOUDFLARE_TOKEN=${CLOUDFLARE_API_KEY:-$CLOUDFLARE_KEY}
CLOUDFLARE_EMAIL=${CLOUDFLARE_EMAIL:-""}
ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID:-"f76d25b8b86cfa5638f43016510d8f77"}

# Check if required environment variables are set
if [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    echo -e "${RED}❌ Error: R2 credentials not found${NC}"
    echo "Please set CLOUDFLARE_R2_ACCESS_KEY_ID and CLOUDFLARE_R2_SECRET_ACCESS_KEY"
    exit 1
fi

# Check for Cloudflare API access
if [ -z "$CLOUDFLARE_TOKEN" ] || [ -z "$CLOUDFLARE_EMAIL" ]; then
    echo -e "${YELLOW}⚠ Warning: Cloudflare API credentials not complete${NC}"
    echo "  Need CLOUDFLARE_API_KEY and CLOUDFLARE_EMAIL for DNS setup"
    SKIP_DNS_SETUP=true
else
    SKIP_DNS_SETUP=false
    echo -e "${GREEN}✓ Using Cloudflare API with email: $CLOUDFLARE_EMAIL${NC}"
fi

# Configuration
BUCKET_NAME="lee-app-nz"
DOMAIN="lee.app.nz"
ZONE_NAME="app.nz"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Account ID: $ACCOUNT_ID"
echo "  Bucket: $BUCKET_NAME"
echo "  Domain: $DOMAIN"
echo ""

# Function to make Cloudflare API calls
cf_api() {
    local method=$1
    local endpoint=$2
    local data=$3
    
    # Use API Key + Email authentication
    if [ -z "$data" ]; then
        curl -s -X "$method" \
            "https://api.cloudflare.com/client/v4/$endpoint" \
            -H "X-Auth-Key: $CLOUDFLARE_TOKEN" \
            -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
            -H "Content-Type: application/json"
    else
        curl -s -X "$method" \
            "https://api.cloudflare.com/client/v4/$endpoint" \
            -H "X-Auth-Key: $CLOUDFLARE_TOKEN" \
            -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
            -H "Content-Type: application/json" \
            -d "$data"
    fi
}

# Step 1: Create R2 bucket if it doesn't exist
echo -e "${YELLOW}Step 1: Checking R2 bucket...${NC}"
BUCKET_CHECK=$(cf_api GET "accounts/$ACCOUNT_ID/r2/buckets/$BUCKET_NAME")

if echo "$BUCKET_CHECK" | grep -q '"success":false'; then
    echo "Creating bucket $BUCKET_NAME..."
    CREATE_RESULT=$(cf_api PUT "accounts/$ACCOUNT_ID/r2/buckets/$BUCKET_NAME" '{"name":"'$BUCKET_NAME'"}')
    
    if echo "$CREATE_RESULT" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ Bucket created successfully${NC}"
    else
        echo -e "${RED}❌ Failed to create bucket${NC}"
        echo "$CREATE_RESULT" | jq '.'
        exit 1
    fi
else
    echo -e "${GREEN}✓ Bucket already exists${NC}"
fi

# Step 2: Configure bucket for public access
echo -e "${YELLOW}Step 2: Configuring bucket for public access...${NC}"

# Enable public access on the bucket
PUBLIC_CONFIG=$(cf_api PUT "accounts/$ACCOUNT_ID/r2/buckets/$BUCKET_NAME/public" '{
    "enabled": true,
    "custom_domain": {
        "domain": "'$DOMAIN'",
        "enabled": true
    }
}')

if echo "$PUBLIC_CONFIG" | grep -q '"success":true'; then
    echo -e "${GREEN}✓ Public access configured${NC}"
else
    # Try alternative approach - set up custom domain
    CUSTOM_DOMAIN=$(cf_api PUT "accounts/$ACCOUNT_ID/r2/buckets/$BUCKET_NAME/custom_domains" '{
        "domain": "'$DOMAIN'"
    }')
    
    if echo "$CUSTOM_DOMAIN" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ Custom domain configured${NC}"
    else
        echo -e "${YELLOW}⚠ Could not configure custom domain automatically${NC}"
        echo "You may need to configure this in the Cloudflare dashboard"
    fi
fi

# Step 3: Get Zone ID for the domain
echo -e "${YELLOW}Step 3: Getting zone information...${NC}"
ZONE_INFO=$(cf_api GET "zones?name=$ZONE_NAME")
ZONE_ID=$(echo "$ZONE_INFO" | jq -r '.result[0].id // empty')

if [ -z "$ZONE_ID" ]; then
    echo -e "${RED}❌ Could not find zone for $ZONE_NAME${NC}"
    echo "Please ensure the domain is added to your Cloudflare account"
    exit 1
fi

echo -e "${GREEN}✓ Found zone ID: $ZONE_ID${NC}"

# Step 4: Create CNAME record for custom domain
echo -e "${YELLOW}Step 4: Setting up DNS records...${NC}"

# Check if CNAME already exists
DNS_RECORDS=$(cf_api GET "zones/$ZONE_ID/dns_records?type=CNAME&name=$DOMAIN")
EXISTING_RECORD=$(echo "$DNS_RECORDS" | jq -r '.result[0].id // empty')

CNAME_TARGET="${BUCKET_NAME}.${ACCOUNT_ID}.r2.cloudflarestorage.com"

if [ -n "$EXISTING_RECORD" ]; then
    echo "Updating existing CNAME record..."
    UPDATE_RESULT=$(cf_api PUT "zones/$ZONE_ID/dns_records/$EXISTING_RECORD" '{
        "type": "CNAME",
        "name": "'$DOMAIN'",
        "content": "'$CNAME_TARGET'",
        "proxied": true,
        "ttl": 1
    }')
    
    if echo "$UPDATE_RESULT" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ CNAME record updated${NC}"
    else
        echo -e "${RED}❌ Failed to update CNAME record${NC}"
        echo "$UPDATE_RESULT" | jq '.'
    fi
else
    echo "Creating new CNAME record..."
    CREATE_RESULT=$(cf_api POST "zones/$ZONE_ID/dns_records" '{
        "type": "CNAME",
        "name": "'$DOMAIN'",
        "content": "'$CNAME_TARGET'",
        "proxied": true,
        "ttl": 1
    }')
    
    if echo "$CREATE_RESULT" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ CNAME record created${NC}"
    else
        echo -e "${RED}❌ Failed to create CNAME record${NC}"
        echo "$CREATE_RESULT" | jq '.'
    fi
fi

# Step 5: Configure bucket CORS (for web hosting)
echo -e "${YELLOW}Step 5: Configuring CORS for web hosting...${NC}"

CORS_CONFIG=$(cf_api PUT "accounts/$ACCOUNT_ID/r2/buckets/$BUCKET_NAME/cors" '[{
    "allowedOrigins": ["*"],
    "allowedMethods": ["GET", "HEAD"],
    "allowedHeaders": ["*"],
    "exposeHeaders": ["ETag"],
    "maxAgeSeconds": 3600
}]')

if echo "$CORS_CONFIG" | grep -q '"success":true'; then
    echo -e "${GREEN}✓ CORS configured${NC}"
else
    echo -e "${YELLOW}⚠ Could not configure CORS automatically${NC}"
fi

# Step 6: Set up index document behavior with a Worker (optional)
echo -e "${YELLOW}Step 6: Worker setup for index.html routing...${NC}"
echo -e "${BLUE}ℹ Note: For proper index.html routing, you may want to create a Cloudflare Worker${NC}"

cat > worker.js << 'EOF'
// Cloudflare Worker for R2 static site hosting
// Deploy this as a Worker and route it to lee.app.nz

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Handle directory paths by adding index.html
    let key = url.pathname.slice(1);
    
    if (!key) {
      key = 'index.html';
    } else if (key.endsWith('/')) {
      key += 'index.html';
    }
    
    // Try to fetch from R2
    const object = await env.BUCKET.get(key);
    
    if (object === null) {
      // Try with .html extension
      const htmlObject = await env.BUCKET.get(key + '.html');
      if (htmlObject !== null) {
        return new Response(htmlObject.body, {
          headers: {
            'content-type': 'text/html;charset=UTF-8',
          },
        });
      }
      
      // Return 404
      return new Response('Not Found', { status: 404 });
    }
    
    // Set appropriate content-type
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('etag', object.httpEtag);
    
    // Guess content-type if not set
    if (!headers.get('content-type')) {
      if (key.endsWith('.html')) headers.set('content-type', 'text/html;charset=UTF-8');
      else if (key.endsWith('.css')) headers.set('content-type', 'text/css');
      else if (key.endsWith('.js')) headers.set('content-type', 'application/javascript');
      else if (key.endsWith('.json')) headers.set('content-type', 'application/json');
      else if (key.endsWith('.png')) headers.set('content-type', 'image/png');
      else if (key.endsWith('.jpg') || key.endsWith('.jpeg')) headers.set('content-type', 'image/jpeg');
      else if (key.endsWith('.webp')) headers.set('content-type', 'image/webp');
      else if (key.endsWith('.svg')) headers.set('content-type', 'image/svg+xml');
    }
    
    return new Response(object.body, {
      headers,
    });
  },
};
EOF

echo -e "${GREEN}Worker code saved to worker.js${NC}"
echo ""
echo -e "${BLUE}To deploy the Worker:${NC}"
echo "1. Go to Cloudflare Dashboard > Workers & Pages"
echo "2. Create a new Worker"
echo "3. Paste the contents of worker.js"
echo "4. Bind the R2 bucket (BUCKET = $BUCKET_NAME)"
echo "5. Add a custom domain route for $DOMAIN"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ R2 Bucket Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  • Bucket: $BUCKET_NAME"
echo "  • Domain: $DOMAIN"
echo "  • CNAME: $DOMAIN → $CNAME_TARGET"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Deploy your site: npm run deploy"
echo "2. Visit: https://$DOMAIN"
echo ""
echo -e "${YELLOW}Optional: For better static site support:${NC}"
echo "  Deploy the generated worker.js to handle index.html routing"
echo ""

# Test the setup
echo -e "${YELLOW}Testing the setup...${NC}"
echo "Waiting 5 seconds for DNS propagation..."
sleep 5

# Try to access the site
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN" || echo "000")

if [ "$RESPONSE" = "200" ]; then
    echo -e "${GREEN}✅ Site is accessible at https://$DOMAIN${NC}"
elif [ "$RESPONSE" = "404" ]; then
    echo -e "${YELLOW}⚠ Site is reachable but no index.html found. Run 'npm run deploy' to upload content${NC}"
else
    echo -e "${YELLOW}⚠ Site not yet accessible (HTTP $RESPONSE). DNS may still be propagating${NC}"
    echo "  This can take a few minutes. Try again shortly."
fi