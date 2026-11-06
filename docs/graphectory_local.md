# Graphectory

[Graphectory](https://github.com/Intelligent-CAT-Lab/Graphectory) draws an
agent run as an interactive trajectory graph. OpenDraco shows it in the
Results page's **Graphectory** tab. Everything runs on your machine:

| Piece | What it is |
|---|---|
| **Viewer** | Graphectory's own web app, run as the Docker container `graphectory-viewer` from the `graphectory` image. You build and run it with docker; OpenDraco never starts, creates or removes it. |
| **Converter** | Part of OpenDraco (`opendraco/utils/graphectory_converter/`, from [OpenDraco/graphectory-opendraco](https://github.com/OpenDraco/graphectory-opendraco)). It turns a run's log into a trajectory the Viewer reads and writes it to `<RESULTS_DIR>/graphectory/`, the folder the container reads as `/data`. Nothing to install. |

The converter flattens a whole multi-agent run into one "super-agent"
trajectory: every agent's activations in run order, each opened by a
*recall* step naming the agent and what it received. Graphectory itself is
not modified. One run = one graph.

Checked against Graphectory commit `5f456b1` (2026-10-28).

## Set it up

The installer can do steps 1 and 2: when Docker is present, `install.sh` /
`install.ps1` ask *"Set up Graphectory locally?"* (`-y` answers yes). By
hand, from the OpenDraco checkout's root:

**1. Build the image** (once; a few minutes, about 2.5 GB). The clone is
git-ignored:

```bash
git clone https://github.com/Intelligent-CAT-Lab/Graphectory.git Graphectory
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

- Every inference run that ends is converted into the Viewer in the
  background. On the Results page, the run's **Graphectory** tab shows its
  graph.
- **Analyze in Graphectory** converts the selected run on demand, for
  example a run from before Graphectory was set up, and shows its graph.
- The Viewer itself is at <http://localhost:9610>, listing every converted
  run.

To convert all the runs you already have in one go:

```bash
~/.opendraco-venv/bin/python scripts/graphectory_convert.py
```

The tab embeds the Viewer only when it is on another origin than the app.
`http://localhost:9610` and the frontend's `http://localhost:4200` differ by
port, so the graph is embedded. The tab asks the Viewer for the same view
options its own page uses by default (`unique_think=false`,
`thought_quotes=true`, …), so the embedded graph matches
<http://localhost:9610>.

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
  converted runs stay with your results), along with the rest of the
  OpenDraco install and the `.env` files.
- **Turn it off:** empty `GRAPHECTORY_URL` and restart the API. The tab then
  only says the setting is missing.

## Troubleshooting

| Symptom | Fix |
|---|---|
| *Could not reach the Graphectory Viewer* | Run `opendraco status`: it says whether the container is missing or stopped and gives the command. `docker logs graphectory-viewer` shows why it stopped. |
| *The Graphectory Viewer does not list run …* | The container reads another folder. `opendraco status` names it and gives the `docker rm -f` + `docker run` to re-create it on `<RESULTS_DIR>/graphectory`. |
| *port is already allocated* from `docker run` | Something else uses that port: pick another one (see *Another port*). |
| The tab shows the link but no graph | The Viewer is on the app's origin, or the frontend is served over `https` (the browser blocks an `http` page inside it); use **New tab**. |
