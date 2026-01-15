module.exports = {
  apps: [{
    name: 'spectro-backend',
    script: 'app_working.py',
    interpreter: 'python3',
    cwd: '/var/www/app.clovitek.com/spectro-backend',
    env: {
      OPENAI_API_KEY: 'your-openai-api-key-here',
      AWS_ACCESS_KEY_ID: 'your-aws-access-key-here',
      AWS_SECRET_ACCESS_KEY: 'your-aws-secret-key-here',
      AWS_REGION: 'us-east-1',
      S3_BUCKET: 'your-s3-bucket-name'
    }
  }]
};
