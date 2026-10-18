# feeds/: camera feeds (owner: Mina)
`feeds.base` plays every camera's clip from a site's `cameras.json` on one run clock and yields `FramePacket`s in time order (`open_feeds`, `FrameBuffer`; contract in `contracts/README.md`).
`python -m feeds.replay --cameras data/sites/annex_clip1/cameras.json --check` opens every clip; without `--check` it plays them and publishes `camera_status`. Clips stay in `data/raw/`, never in git; `fake_clips.py` makes synthetic test clips.
