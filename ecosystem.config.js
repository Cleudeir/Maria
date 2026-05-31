module.exports = {
  apps: [
    {
      name: "maria",
      script: "./backend/server.py",
      interpreter: "./.venv/bin/python",
      cwd: __dirname,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        FLASK_ENV: "production",
        MARIA_SERVER: "1",
      },
      env_production: {
        DEBUG: "0",
        MARIA_SERVER: "1",
      },
    },
    {
      name: "maria-frontend",
      script: "npx",
      args: "vite --host 0.0.0.0 --port 10001",
      cwd: "./frontend",
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development",
      },
    },
  ],
};
