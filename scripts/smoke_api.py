"""Quick REST smoke test for the FastAPI app — not a pytest target."""
from fastapi.testclient import TestClient
from kinetic_ranger.api.main import app


def main() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
        print("health", r.status_code, r.json())

        r = client.get("/source")
        print("source", r.status_code, r.json())

        r = client.get("/runs")
        print("runs", r.status_code, "count=", len(r.json()))

        r = client.get("/runs/record/status")
        print("rec_status", r.status_code, r.json())

        r = client.post("/source/pause")
        print("pause_on_sim_should_409", r.status_code, r.json())

        r = client.post("/runs/record/start")
        print("rec_start", r.status_code, r.json())

        r = client.post("/runs/record/start")
        print("rec_start_again_should_409", r.status_code, r.json())

        r = client.post("/runs/record/stop")
        print("rec_stop", r.status_code, r.json())

        r = client.get("/runs")
        runs = r.json()
        print("runs_after_record count=", len(runs))
        if runs:
            run_id = runs[0]["run_id"]
            print("first_run", run_id, "peak=", runs[0]["peak_severity"])

            r = client.get(f"/runs/{run_id}/timeline")
            print("timeline", r.status_code, "points=", len(r.json()))

            r = client.post(f"/runs/{run_id}/load")
            print("load_replay", r.status_code, r.json())

            r = client.post("/source/pause")
            print("pause_on_replay", r.status_code, r.json())

            r = client.post("/source/seek", json={"frame": 5})
            print("seek_to_5", r.status_code, r.json())

            r = client.post("/source/play")
            print("play", r.status_code, r.json())

            r = client.post("/source/live")
            print("back_to_live", r.status_code, r.json())


if __name__ == "__main__":
    main()
