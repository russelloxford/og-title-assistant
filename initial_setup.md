# OG Title Assistant - Initial Setup Guide

This guide walks you through setting up all required accounts and services for the OG Title Assistant application.

---

## Prerequisites

- Python 3.11 or higher installed
- A credit card for cloud service accounts (most have free tiers)
- Basic familiarity with command line operations

---

## 1. Anthropic Claude API Account

Claude AI is used for extracting document metadata from the body of legal documents.

### Steps:

1. **Create an Account**
   - Go to [https://console.anthropic.com/](https://console.anthropic.com/)
   - Click "Sign Up" and create your account
   - Verify your email address

2. **Add Payment Method**
   - Navigate to "Settings" → "Billing"
   - Add a credit card (required for API access)
   - Set a spending limit to control costs

3. **Generate API Key**
   - Go to "Settings" → "API Keys"
   - Click "Create Key"
   - Name it something descriptive (e.g., "og-title-assistant-prod")
   - **Copy and save the key immediately** - it won't be shown again

4. **Store the API Key**
   ```bash
   # Add to your environment variables
   export ANTHROPIC_API_KEY="sk-ant-api03-..."

   # Or add to .env file in project root
   echo 'ANTHROPIC_API_KEY=sk-ant-api03-...' >> .env
   ```

### Estimated Cost:
- Claude Sonnet 4.5: $3.00/MTok input, $15.00/MTok output
- Typical document body extraction: ~$0.08 per document

---

## 2. AWS Account (for Textract and S3)

AWS Textract is used for extracting tabular data from lease schedule exhibits. S3 is used for temporary file storage during processing.

### Steps:

1. **Create an AWS Account**
   - Go to [https://aws.amazon.com/](https://aws.amazon.com/)
   - Click "Create an AWS Account"
   - Follow the registration process (requires credit card)
   - Choose the "Free Tier" option

2. **Create an IAM User**
   - Log into AWS Console
   - Go to "IAM" service
   - Click "Users" → "Create user"
   - Name: `og-title-assistant`
   - Check "Programmatic access"

3. **Attach Permissions**
   - On the permissions page, click "Attach policies directly"
   - Search for and attach these policies:
     - `AmazonTextractFullAccess`
     - `AmazonS3FullAccess` (or create a more restrictive custom policy)

4. **Create Access Keys**
   - After creating the user, click on the user name
   - Go to "Security credentials" tab
   - Click "Create access key"
   - Choose "Application running outside AWS"
   - **Save both the Access Key ID and Secret Access Key**

5. **Create S3 Bucket**
   - Go to S3 service
   - Click "Create bucket"
   - Name: `og-title-assistant-temp-[your-unique-id]`
   - Region: `us-east-1` (recommended for Textract)
   - Enable "Block all public access"

6. **Set Lifecycle Rule for Auto-Cleanup**
   - Click on your bucket → "Management" tab
   - Click "Create lifecycle rule"
   - Rule name: `auto-delete-temp-files`
   - Apply to all objects in bucket
   - Under "Lifecycle rule actions", check "Expire current versions of objects"
   - Set "Days after object creation": `1`

7. **Store Credentials**
   ```bash
   # Add to your environment variables
   export AWS_ACCESS_KEY_ID="AKIA..."
   export AWS_SECRET_ACCESS_KEY="..."
   export AWS_DEFAULT_REGION="us-east-1"
   export TEXTRACT_S3_BUCKET="og-title-assistant-temp-[your-unique-id]"

   # Or add to .env file
   echo 'AWS_ACCESS_KEY_ID=AKIA...' >> .env
   echo 'AWS_SECRET_ACCESS_KEY=...' >> .env
   echo 'AWS_DEFAULT_REGION=us-east-1' >> .env
   echo 'TEXTRACT_S3_BUCKET=og-title-assistant-temp-...' >> .env
   ```

### Estimated Cost:
- Textract Tables: $0.015 per page
- S3 Storage: Minimal (~$0.023/GB/month, files deleted after 1 day)

---

## 3. Neo4j Aura Account

Neo4j is used as a graph database for modeling chain of title relationships.

### Steps:

1. **Create an Account**
   - Go to [https://neo4j.com/cloud/aura/](https://neo4j.com/cloud/aura/)
   - Click "Start Free"
   - Create account (can use Google/GitHub SSO)

2. **Create a Free Instance**
   - Click "New Instance"
   - Choose "AuraDB Free" tier
   - Name: `og-title-assistant`
   - Region: Choose closest to you
   - Click "Create"

3. **Save Connection Details**
   - **IMPORTANT**: When the instance is created, you'll see a one-time password
   - **Copy and save this password immediately**
   - Note the connection URI (format: `neo4j+s://xxxxx.databases.neo4j.io`)

4. **Store Connection Details**
   ```bash
   # Add to your environment variables
   export NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io"
   export NEO4J_USERNAME="neo4j"
   export NEO4J_PASSWORD="..."

   # Or add to .env file
   echo 'NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io' >> .env
   echo 'NEO4J_USERNAME=neo4j' >> .env
   echo 'NEO4J_PASSWORD=...' >> .env
   ```

5. **Verify Connection**
   - Click "Open with Neo4j Browser" on your instance
   - Enter your credentials
   - Run a test query: `RETURN 1`

### Free Tier Limits:
- 50,000 nodes
- 175,000 relationships
- Sufficient for initial development and testing

---

## 4. Google Cloud Platform Account (Optional - for Cloud Run deployment)

GCP is used for deploying the application to Cloud Run for production use.

### Steps:

1. **Create a GCP Account**
   - Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
   - Sign in with Google account
   - Accept terms and set up billing

2. **Create a New Project**
   - Click project dropdown → "New Project"
   - Name: `og-title-assistant`
   - Click "Create"

3. **Enable Required APIs**
   - Go to "APIs & Services" → "Enable APIs and Services"
   - Search for and enable:
     - Cloud Run API
     - Cloud Build API
     - Artifact Registry API

4. **Install gcloud CLI**
   ```bash
   # macOS
   brew install google-cloud-sdk

   # Linux
   curl https://sdk.cloud.google.com | bash

   # Initialize
   gcloud init
   gcloud auth application-default login
   ```

5. **Store Project ID**
   ```bash
   export GCP_PROJECT_ID="og-title-assistant"
   echo 'GCP_PROJECT_ID=og-title-assistant' >> .env
   ```

### Estimated Cost:
- Cloud Run: Pay-per-use (~$0.00002400/vCPU-second)
- Typically ~$20/month for moderate usage

---

## 5. Install Tesseract OCR (Local - No Account Required)

Tesseract is used locally for the intelligent document splitter. No cloud account needed.

### Installation:

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

**Windows:**
1. Download installer from [UB-Mannheim GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
2. Run the installer
3. Add to PATH: `C:\Program Files\Tesseract-OCR`

### Verify Installation:
```bash
tesseract --version
```

Expected output: `tesseract 5.x.x` (version may vary)

---

## 6. Environment Configuration Summary

Create a `.env` file in your project root with all credentials:

```bash
# .env file - DO NOT COMMIT TO GIT

# Anthropic Claude API
ANTHROPIC_API_KEY=sk-ant-api03-...

# AWS Credentials
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
TEXTRACT_S3_BUCKET=og-title-assistant-temp-...

# Neo4j Aura
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...

# Optional: Google Cloud Platform
GCP_PROJECT_ID=og-title-assistant
```

**IMPORTANT:** Add `.env` to your `.gitignore` file:
```bash
echo '.env' >> .gitignore
```

---

## 7. Python Environment Setup

After all accounts are configured:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
.\venv\Scripts\activate

# Install dependencies
pip install \
  pymupdf \
  pytesseract \
  pillow \
  boto3 \
  anthropic \
  neo4j \
  pandas \
  streamlit \
  amazon-textract-response-parser \
  python-dotenv

# Create requirements.txt
pip freeze > requirements.txt
```

---

## 8. Verification Checklist

Run through this checklist to verify all services are configured correctly:

- [ ] **Anthropic API**: Run `python -c "import anthropic; print(anthropic.Anthropic().models.list())"`
- [ ] **AWS Credentials**: Run `aws sts get-caller-identity`
- [ ] **S3 Bucket**: Run `aws s3 ls s3://your-bucket-name`
- [ ] **Textract**: Upload a test PDF and verify table extraction
- [ ] **Neo4j**: Connect via Neo4j Browser and run `RETURN 1`
- [ ] **Tesseract**: Run `tesseract --version`

---

## Troubleshooting

### Anthropic API Issues
- **401 Unauthorized**: Check API key is correct and has no extra whitespace
- **402 Payment Required**: Add payment method to your account
- **Rate Limited**: Implement exponential backoff in your code

### AWS Issues
- **Access Denied**: Verify IAM policies are attached correctly
- **Region Mismatch**: Ensure bucket and Textract are in same region
- **S3 Upload Fails**: Check bucket name is globally unique

### Neo4j Issues
- **Connection Refused**: Verify URI format includes `neo4j+s://` (with encryption)
- **Authentication Failed**: Password may have expired; reset in Aura console
- **Query Timeout**: Free tier has limited resources; optimize queries

### Tesseract Issues
- **Command Not Found**: Ensure Tesseract is in your system PATH
- **Language Data Missing**: Install additional language packs if needed

---

## Cost Summary (Monthly Estimates)

| Service | Free Tier | Typical Usage |
|---------|-----------|---------------|
| Anthropic Claude | - | ~$120/month (1000 docs) |
| AWS Textract | 1000 pages/month free | ~$50/month |
| AWS S3 | 5GB free | ~$5/month |
| Neo4j Aura | 50K nodes free | $0 (free tier) |
| GCP Cloud Run | 2M requests free | ~$20/month |
| **TOTAL** | - | **~$195/month** |

---

## Next Steps

Once all accounts are set up and verified:

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your credentials
3. Run `pip install -r requirements.txt`
4. Start with Phase 1: Document Splitter implementation
5. Test with sample documents from the `test_documents/` folder

For questions or issues, refer to the service documentation:
- [Anthropic Docs](https://docs.anthropic.com/)
- [AWS Textract Docs](https://docs.aws.amazon.com/textract/)
- [Neo4j Aura Docs](https://neo4j.com/docs/aura/)
- [Tesseract Docs](https://github.com/tesseract-ocr/tesseract)
