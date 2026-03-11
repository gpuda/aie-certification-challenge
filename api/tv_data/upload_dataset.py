import json
from pathlib import Path
from dotenv import load_dotenv
from langsmith import Client

# Load env from api/.env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = Client()

dataset = client.create_dataset(
    dataset_name="tv-testset",
    description="TV analytics evaluation dataset from testset_tv.json"
)

with open("tv_data/testset_tv.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    client.create_example(
        dataset_id=dataset.id,
        inputs={
            "question": item["user_input"]
        },
        outputs={
            "answer": item["reference"]
        },
        metadata={
            "reference_contexts": item.get("reference_contexts"),
            "persona_name": item.get("persona_name"),
            "query_style": item.get("query_style"),
            "query_length": item.get("query_length"),
            "synthesizer_name": item.get("synthesizer_name"),
        }
    )

print(f"Uploaded {len(data)} examples to dataset: {dataset.name}")
