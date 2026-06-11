This folder contains legacy backups of top-level HTML files that were found in the repository root.

Files moved here:
- auth-live.html
- profile-live.html
- profile-origin.html
- profile-prod.html

Reason:
The project uses `medqueue/startup/html` as the canonical frontend source (these files are copied into Docker images). Top-level HTML files at the repository root were duplicates and could cause confusion. They were moved here as a safe backup so the repository structure is consistent.

If you need to restore any file to the project root, copy it back from this folder. Before deploying, ensure paths to `../css/` and `../js/` are correct relative to the file location.
