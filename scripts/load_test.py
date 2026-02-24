import asyncio
import httpx
import time
import os
import statistics
from collections import Counter

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TOTAL_REQUESTS = int(os.getenv("TOTAL_REQUESTS", "250"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "50"))

async def run_workflow(client: httpx.AsyncClient, i: int, semaphore: asyncio.Semaphore):
    async with semaphore:
        try:
            # Submit a simple but valid DAG
            payload = {
                "name": f"Load Test {i}",
                "dag": {
                    "nodes": [
                        {"id": "step1", "handler": "input", "dependencies": []},
                        {"id": "step2", "handler": "output", "dependencies": ["step1"]}
                    ]
                }
            }
            
            start = time.time()
            resp = await client.post("/api/v1/workflow", json=payload)
            resp.raise_for_status()
            
            exec_id = resp.json()["execution_id"]
            
            # Trigger
            await client.post(f"/api/v1/workflow/trigger/{exec_id}")
            
            # Poll for completion with a timeout
            timeout_at = time.time() + 30
            while time.time() < timeout_at:
                resp = await client.get(f"/api/v1/workflow/{exec_id}")
                if resp.status_code != 200:
                    return f"POLL_ERROR_{resp.status_code}", time.time() - start
                
                data = resp.json()
                status = data.get("status")
                if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    return status, time.time() - start
                
                await asyncio.sleep(0.1) # Polling interval
            
            return "POLL_TIMEOUT", 30
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return "RATE_LIMITED", 0
            if e.response.status_code == 503:
                return "CIRCUIT_OPEN", 0
            return f"HTTP_ERROR_{e.response.status_code}", 0
        except Exception as e:
            return f"EXCEPTION_{type(e).__name__}", 0

async def main():
    print(f"🚀 Workflow Orchestrator: High-Throughput Load Test")
    print(f"Target:      {BASE_URL}")
    print(f"Requests:    {TOTAL_REQUESTS}")
    print(f"Concurrency: {CONCURRENCY}")
    
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        start_time = time.time()
        tasks = [run_workflow(client, i, semaphore) for i in range(TOTAL_REQUESTS)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Aggregate stats
        statuses = [r[0] for r in results]
        durations = [r[1] for r in results if r[0] == "COMPLETED"]
        counter = Counter(statuses)
        
        print("\n" + "="*40)
        print("  LOAD TEST SUMMARY")
        print("="*40)
        print(f"Total Time:     {total_time:.2f}s")
        print(f"Throughput:     {TOTAL_REQUESTS / total_time:.2f} workflows/sec")
        print("-" * 40)
        
        for status, count in counter.items():
            color = "\033[0;32m" if status == "COMPLETED" else "\033[0;31m"
            print(f"{color}{status:20}\033[0m: {count}")
            
        if durations:
            print("-" * 40)
            print(f"Latency P50:    {statistics.median(durations):.3f}s")
            if len(durations) >= 2:
                print(f"Latency P95:    {statistics.quantiles(durations, n=20)[18]:.3f}s")
                print(f"Latency P99:    {statistics.quantiles(durations, n=100)[98]:.3f}s")
            print(f"Avg Duration:   {sum(durations)/len(durations):.3f}s")
        print("="*40)

if __name__ == "__main__":
    asyncio.run(main())
