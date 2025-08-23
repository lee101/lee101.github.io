#!/bin/bash

# Build script for lee.app.nz

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🛠️  Building lee.app.nz${NC}"

# Clean build directory
echo -e "${YELLOW}Cleaning build directory...${NC}"
rm -rf build
mkdir -p build

# Build CSS from LESS
echo -e "${YELLOW}Building CSS from LESS...${NC}"
npm run build

# Copy static files
echo -e "${YELLOW}Copying static files...${NC}"
cp -r static build/
cp index.html build/

# Copy other root files if they exist
for file in favicon.ico robots.txt sitemap.xml; do
    if [ -f "$file" ]; then
        cp "$file" build/
        echo "  Copied $file"
    fi
done

# Create a simple .gitignore for the build folder
echo -e "${YELLOW}Creating build .gitignore...${NC}"
cat > build/.gitignore << EOF
# Build directory - not tracked
*
!.gitignore
EOF

echo -e "${GREEN}✅ Build complete!${NC}"
echo -e "Build output in: ${GREEN}build/${NC}"

# Check build size
BUILD_SIZE=$(du -sh build | cut -f1)
echo -e "Build size: ${YELLOW}$BUILD_SIZE${NC}"