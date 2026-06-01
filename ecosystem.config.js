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
        PORT: "10010",
      },
      env_production: {
        DEBUG: "0",
        MARIA_SERVER: "1",
        PORT: "10010",
      },
    },
  ],
};
