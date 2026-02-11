/**
 * PM2 process config — runs the API, UI, and worker.
 *   pm2 start ecosystem.config.js
 *   pm2 status
 *   pm2 restart all
 */
module.exports = {
  apps: [
    {
      name: 'api',
      script: 'uv',
      args: 'run uvicorn lib.api.app:app --reload',
      watch: false,
    },
    {
      name: 'ui',
      script: 'uv',
      args: 'run python3 -m streamlit run lib/ui/streamlit_app.py',
      watch: false,
    },
    {
      name: 'worker',
      script: 'uv',
      args: 'run python3 -m lib.bin.worker',
      watch: false,
    },
  ],
};
