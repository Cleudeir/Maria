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
        LLAMACPP_API_KEY: "0c95d03b-52a6-4c19-99b2-f0f6661db6ef",
      },
      env_production: {
        DEBUG: "0",
        MARIA_SERVER: "1",
        PORT: "10010",
        LLAMACPP_API_KEY: "0c95d03b-52a6-4c19-99b2-f0f6661db6ef",
      },
    },
    {
      name: "maria-frontend",
      script: "pnpm",
      args: "dev --host --port 10011",
      cwd: __dirname + "/frontend",
      exec_mode: "fork",
      autorestart: true,
      watch: true,
      watch_delay: 1000,
      ignore_watch: ["node_modules", "dist"],
    },
  ],
};
