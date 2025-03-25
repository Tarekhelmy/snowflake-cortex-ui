# Deployment Instructions for Snowflake Cortex Chat Interface

This document outlines the steps needed to deploy the Snowflake Cortex Chat application. The application consists of an HTML/CSS/JavaScript frontend and a Python FastAPI backend that connects to Snowflake's Cortex analyst service.

## Requirements

1. Python 3.8+ with pip
2. Snowflake account with Cortex enabled
3. Basic familiarity with command-line operations

## Setup Steps

### 1. Set Up the Environment

First, create a project directory and set up a virtual environment:

```bash
# Create project directory
mkdir snowflake-cortex-chat
cd snowflake-cortex-chat

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

Install the required Python packages:

```bash
pip install fastapi uvicorn snowflake-connector-python python-dotenv jinja2
```

### 3. Create Environment Configuration

Create a `.env` file in the project root with your Snowflake credentials:

```
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_ACCOUNT=your_account_identifier
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
```

### 4. Create Project Structure

Set up the project directories:

```bash
mkdir templates
```

### 5. Save the Backend Code

Create a file named `main.py` in the project root and copy the FastAPI backend code from the `fastapi-backend-python` artifact.

### 6. Save the Frontend HTML

Create a file named `index.html` in the `templates` directory and copy the HTML content from the `html-frontend` artifact.

### 7. Configure Cortex Query

Open `main.py` and ensure that the `query_cortex` function correctly interacts with your specific Snowflake Cortex setup. You may need to adjust the SQL query format based on how Cortex is configured in your Snowflake environment.

### 8. Run the Application

Start the FastAPI server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The application should now be accessible at http://localhost:8000

## Production Deployment Considerations

For a production deployment, consider the following:

1. **Database Integration**: Replace the in-memory storage with a proper database like PostgreSQL or MongoDB
2. **Authentication**: Add user authentication to protect sensitive data
3. **HTTPS**: Configure secure connections using HTTPS
4. **Rate Limiting**: Implement rate limiting to prevent abuse
5. **CORS**: Restrict CORS to only allow specific origins
6. **Environment Variables**: Use a secure method to manage environment variables
7. **Logging**: Implement comprehensive logging
8. **Error Handling**: Enhance error handling for production scenarios
9. **Monitoring**: Add monitoring and alerting
10. **Containerization**: Consider containerizing the application using Docker

## Deployment Options

### Option 1: Traditional Server

Deploy on a VM or dedicated server with Nginx as a reverse proxy:

```bash
# Install Nginx
sudo apt update
sudo apt install nginx

# Configure Nginx as reverse proxy
sudo nano /etc/nginx/sites-available/cortex-chat
```

Add this configuration:

```
server {
    listen 80;
    server_name your_domain_or_ip;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/cortex-chat /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

### Option 2: Docker Container

Create a `Dockerfile`:

```Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create a `requirements.txt`:

```
fastapi
uvicorn
snowflake-connector-python
python-dotenv
jinja2
```

Build and run the Docker container:

```bash
docker build -t snowflake-cortex-chat .
docker run -p 8000:8000 --env-file .env snowflake-cortex-chat
```

### Option 3: Cloud Deployment

The application can be deployed to cloud platforms like:

- **AWS**: Using Elastic Beanstalk or ECS
- **Google Cloud**: Using Cloud Run or App Engine
- **Azure**: Using App Service or Azure Container Instances
- **Heroku**: For simplified deployment

## Troubleshooting

- **Connection Issues**: Verify Snowflake credentials and network connectivity
- **CORS Errors**: Check CORS configuration in FastAPI
- **Cortex Errors**: Confirm that the Cortex SQL query format is correct for your Snowflake setup
- **Memory Issues**: For large conversation history, implement database storage

## Maintenance

- Regularly update dependencies for security
- Monitor application performance and logs
- Back up conversation data
- Keep Snowflake credentials secure and rotate them periodically