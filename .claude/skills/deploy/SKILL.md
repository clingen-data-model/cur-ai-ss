---
name: deploy
description: Deploy the application to the development environment
disable-model-invocation: true
allowed-tools: Bash(ansible-playbook *)
---

# Deploy Skill

Deploy the application to the dev-caa environment:

```bash
ansible-playbook -i dev-caa.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml -e domain=gene-curation-ai.app
```

After deployment completes, verify the application is running at https://gene-curation-ai.app
