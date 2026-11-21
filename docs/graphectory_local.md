# Graphectory

[Graphectory](https://github.com/Intelligent-CAT-Lab/Graphectory) draws an
agent run as an interactive trajectory graph. OpenDraco shows it in the
Results page's **Graphectory** tab. The usual setup, described first, runs
everything on your machine; the Viewer can also run
[on another machine](#viewer-on-another-machine):

| Piece | What it is |
|---|---|
| **Run log** | Every inference run is recorded as [ATIF](https://docs.harborframework.com/agents/atif) (`ATIF-v1.8`): one `trajectory.json` per instance in `opendraco/logs/inference_logs/<stem>/<instance_id>/`. Multi-agent runs are nested: the root trajectory is the graph engine, each agent activation an embedded subagent trajectory (`<agent>#<n>`). |
| **Viewer** | Graphectory's web app built from the ATIF fork, [xiangfengyepan/Graphectory `feat/atif-mas`](https://github.com/xiangfengyepan/Graphectory/tree/feat/atif-mas), run as the Docker container `graphectory-viewer` from the `graphectory` image. Stock Graphectory cannot read ATIF. You build and run it with docker; OpenDraco never starts, creates or removes it. |

Publishing copies a run's trajectories into `<RESULTS_DIR>/graphectory/<run_id>/<instance_id>/`,
the folder the container reads as `/data` (for a Viewer on another machine
they are uploaded instead). There is no converter: the
Viewer reads ATIF itself and draws one graph per instance (id
`<run_id>.<instance_id>`), inlining every agent activation.

## Set it up

The installer can do steps 1 and 2: when Docker is present, `install.sh` /
`install.ps1` ask *"Set up Graphectory locally?"* (`-y` answers yes). By
hand, from the OpenDraco checkout's root:

**1. Build the image** (once; a few minutes, about 2.5 GB). The clone is
git-ignored:

```bash
git clone -b feat/atif-mas https://github.com/xiangfengyepan/Graphectory.git Graphectory
docker build -t graphectory Graphectory
```

**2. Run the container** on port 9610, reading `results/graphectory/` (the
default `RESULTS_DIR`; use your own `<RESULTS_DIR>/graphectory` if you
changed it):

```bash
# Linux / macOS
mkdir -p results/graphectory
docker run -d --name graphectory-viewer --restart unless-stopped -p 9610:9610 \
  -v "$PWD/results/graphectory:/data" \
  graphectory python graph_construction/live_graph_server.py --port 9610
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force results\graphectory | Out-Null
docker run -d --name graphectory-viewer --restart unless-stopped -p 9610:9610 `
  -v "${PWD}\results\graphectory:/data" `
  graphectory python graph_construction/live_graph_server.py --port 9610
```

`--restart unless-stopped` keeps it running across reboots, so this is a
one-time step.

**3. Enable it** in `opendraco/.env` and restart the API:

```dotenv
GRAPHECTORY_URL="http://localhost:9610"
```

`opendraco status` then checks the Viewer, the image and the container.
When something is off (no image, no container, a stopped container, another
port or another `/data` folder), it prints the docker command that fixes it.

## Use it

Run OpenDraco as usual, `opendraco api` and `opendraco web`:

- Every inference run that ends is published into the Viewer in the
  background. On the Results page, the **Graphectory** tab shows the
  selected instance's graph.
- **Analyze in Graphectory** publishes the selected run on demand, for
  example a run from before Graphectory was set up.
- The Viewer itself is at <http://localhost:9610>, listing every published
  instance.
- Publishing removes any Claude Code sessions an older OpenDraco converter
  left in `results/graphectory/` (the Viewer reads one format per folder,
  and those would hide the ATIF runs).

Runs recorded before ATIF (an `inference_logs/<stem>.ndjson`) are converted
once with the migration script (add `--publish` to also publish them):

```bash
~/.opendraco-venv/bin/python scripts/ndjson_to_atif.py
```

The tab embeds the Viewer only when it is on another origin than the app.
`http://localhost:9610` and the frontend's `http://localhost:4200` differ by
port, so the graph is embedded. The tab asks the Viewer for the same view
options its own page uses by default (`unique_think=false`,
`thought_quotes=true`, …), so the embedded graph matches
<http://localhost:9610>.

## Viewer on another machine

The setup above keeps the Viewer on the machine that runs OpenDraco, where it
reads `results/graphectory/` directly. A Viewer on a server cannot see that
folder, so OpenDraco sends it the runs instead: whenever `GRAPHECTORY_URL` is
not `localhost`, `127.0.0.1` or `::1`, each instance's `trajectory.json` goes
to the Viewer's `POST /api/upload`. Nothing else changes: finished runs are
published on their own and **Analyze in Graphectory** works the same.

**On the server**, start the Viewer with an upload folder. Uploads are refused
without `--upload_dir`, so a Viewer never accepts files unless you ask it to:

```bash
mkdir -p ~/graphectory-data
docker run -d --name graphectory-viewer --restart unless-stopped -p 9610:9610 \
  -v ~/graphectory-data:/data \
  graphectory python graph_construction/live_graph_server.py --port 9610 \
  --trajs /data --upload_dir /data
```

The image runs as user id 10001, which must be able to write to the mounted
folder: `sudo chown 10001 ~/graphectory-data` (or `chmod o+w` it).

**On the OpenDraco machine**, set the Viewer's address exactly as a browser
reaches it, and restart the API:

```dotenv
GRAPHECTORY_URL="https://my-server.example.ts.net:9610"
```

Use `https://` and the certificate's host name when the server is behind
`tailscale serve` or another TLS proxy. Plain `http://` to such a server is
answered with *HTTP 400: Client sent an HTTP request to an HTTPS server*.

`opendraco status` then only checks that the Viewer answers; the local Docker
image and container are not involved. Anyone who can reach the Viewer's port
can upload to it and see every run, so keep it on a private network.

## Managing it

```bash
docker logs -f graphectory-viewer     # the Viewer's output
docker stop graphectory-viewer        # stop it
docker start graphectory-viewer       # start it again
docker rm -f graphectory-viewer       # remove it (then step 2 re-creates it)
```

- **Another port:** remove the container, run step 2 with `-p <port>:9610`,
  and use that port in `GRAPHECTORY_URL`.
- **Update the Viewer:** `git -C Graphectory pull`, rebuild with
  `docker build -t graphectory Graphectory`, then remove the container and
  run step 2 again.
- **Remove a run:** delete its folder from `results/graphectory/`.
- **Remove everything:** `uninstall.sh --purge` / `uninstall.ps1 --purge`
  removes the container, the image and the `Graphectory/` clone (the
  published runs stay with your results), along with the rest of the
  OpenDraco install and the `.env` files.
- **Turn it off:** empty `GRAPHECTORY_URL` and restart the API. The tab then
  only says the setting is missing.

## Troubleshooting

| Symptom | Fix |
|---|---|
| *Could not reach the Graphectory Viewer* | Run `opendraco status`: it says whether the container is missing or stopped and gives the command. `docker logs graphectory-viewer` shows why it stopped. |
| *The Graphectory Viewer does not list …* | Either the image was built from stock Graphectory, which can't read ATIF (rebuild it from the fork's `feat/atif-mas`, step 1), or the container reads another folder: `opendraco status` names it and gives the `docker rm -f` + `docker run` to re-create it on `<RESULTS_DIR>/graphectory`. |
| *The Graphectory Viewer … has no upload endpoint* | The Viewer on the other machine is older than the upload endpoint: update it to the fork's `feat/atif-mas` and start it with `--upload_dir` (see *Viewer on another machine*). |
| *The Graphectory Viewer … refuses uploads* | It was started without `--upload_dir`: add it and restart the Viewer. |
| *POST /api/upload with HTTP 500: Could not write into the upload folder* | The Viewer's user (id 10001 in the image) cannot write to the mounted folder: `chown 10001` it on the server. |
| *HTTP 400* on every request to a remote Viewer | The server speaks HTTPS: use `https://` and its certificate's host name in `GRAPHECTORY_URL`. |
| *port is already allocated* from `docker run` | Something else uses that port: pick another one (see *Another port*). |
| The tab shows the link but no graph | The Viewer is on the app's origin, or the frontend is served over `https` (the browser blocks an `http` page inside it); use **New tab**. |
