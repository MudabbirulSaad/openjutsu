# OpenJutsu

A local video preparation and generation studio. Prepare on your GPU, inspect the conditioning clip, compare cloud previews, and choose a native or locally upscaled export.

**Status:** implementation in progress. Cloud billing and output quality require an account-specific, budgeted pilot. This project does not claim knowledge of Higgsfield's proprietary internals.

## Runtime

Python 3.12, Node.js 22+, pnpm, FFmpeg/FFprobe, and Ubuntu WSL2 on Windows. CUDA models are installed separately. Source media, transcripts, keys, model weights, and job data remain outside Git.

## License

Application source is Apache 2.0. Model weights, dependencies, and imported media retain their own licenses. See [NOTICE](NOTICE).
