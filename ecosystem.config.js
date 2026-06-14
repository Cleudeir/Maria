module.exports = {
  apps: [
    {
      name: "agentic",
      script: "/root/Documents/Server/projetos/Maria/backend/server.py",
      interpreter: "/root/Documents/Server/projetos/Maria/.venv/bin/python",
      cwd: "/root/Documents/Server/projetos/Maria",
      env: {
        MARIA_SERVER: "1",
        PORT: "10010",
      },
    },
    {
      name: "agentic-frontend",
      script: "./node_modules/vite/bin/vite.js",
      args: "--port 10011",
      cwd: __dirname + "/frontend",
      exec_mode: "fork",
      autorestart: true,
      watch: false,
    },
  ],
};
