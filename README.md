# Collaboration 1

ROS2 and React-based robot cooking automation project for Collaboration 1.

## Contents

- `src/cobot1_project/`: ROS2 Python package for task control, cooking motions, recovery, image preprocessing, and Flask/ROS integration.
- `frontend/`: React/Vite dashboard for login, monitoring, task control, and history views.
- `requirements.txt`: Python dependency notes from the original source package.

## Frontend Cleanup

The following frontend files were separated into `../쓰레기통/collaboration-1` because they are not needed in a GitHub source repository:

- `node_modules/`
- empty placeholder components
- backup JSX files such as `Dashboard_backup.jsx` and `LogHistory_backup.jsx`

Install frontend dependencies again with:

```bash
cd frontend
npm install
npm run dev
```

## Archived Materials

Videos, presentation files, PDFs, images, compressed files, generated databases, and original downloaded bundles were moved to `../아카이브`.

## Notes

- This folder is prepared as an independent GitHub repository.
- Media assets referenced by old documentation may now live in `../아카이브`.
- Do not commit generated dependency folders or local robot runtime files.
