git pull && tar -czf jsons.tar.gz jsons && curl -X POST http:/192.168.7.254:4000/api/plugin-repo-update -F "repo_url=https://github.com/BoomerET/drac-ahtcg-plugin" -F "file=@jsons.tar.gz"
