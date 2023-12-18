#!/usr/bin/env python3

from pathlib import Path
from openai import OpenAI
import os
import torch


try:
    openai_api_key = open(Path.home() / ".openai.key", "r").read().strip()
except Exception as err:
    print(f"Failed to retrieve your OpenAI key. Make sure there is a file in your home directory called .openai.key containing the key in plain text. Error: {err}")
    exit()

openai_client = OpenAI(
    api_key = openai_api_key
)

completion = openai_client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "San Francisco is a",
        }
    ],
    model="gpt-3.5-turbo",
    max_tokens=256
)
print(completion)

encoder_path = "/checkpoint/opt_test/original/clinical_llm/models--BAAI--bge-large-zh-v1.5/snapshots/b5c9d86d763d9945f7c0a73e549a4a39c423d520/"
rag_path = "/scratch/ssd002/projects/opt_test/clinical_llm/datasets/rag"
key_path = os.path.join(rag_path, "test_embeddings.pt")
model_path = "/scratch/ssd002/projects/opt_test/Llama-2-7b-chat-hf"
reranker_path = ""
value_path = os.path.join(rag_path, "test_text.pt")

# pip install -U FlagEmbedding
from FlagEmbedding import FlagReranker, FlagModel

class EmbeddingModel:
    def __init__(self, model_name_or_path: str, retrieval_instruction: str):
        self.model = FlagModel(model_name_or_path, query_instruction_for_retrieval=retrieval_instruction, use_fp16=True)


    def __call__(self, queries: list[str]) -> torch.tensor:
        assert isinstance(queries, list)
        return torch.tensor(self.model.encode(queries))


class RerankerModel:
    def __init__(self, model_name_or_path: str):
        self.model = FlagReranker(model_name_or_path, use_fp16=True)
    

    def __call__(self, queries: list[str], retrieved: list[list[str]], k: int, return_scores = False) -> torch.tensor:
        assert isinstance(queries, list)
        assert isinstance(retrieved, list)
        assert len(queries) == len(retrieved)

        rerank_scores = []
        for i in range(len(queries)):
            q = queries[i]
            r = retrieved[i]
            rerank_scores.append(self.model.compute_score([[q, k] for k in r]))
        rerank_scores = torch.tensor(rerank_scores) 
        scores, indices = torch.topk(rerank_scores, k, dim = -1)

        # TODO factor out copy pasted code here
        topk = []
        indices = indices.tolist()
        for i in range(len(indices)):
            slice = indices[i]
            r = retrieved[i]
            topk_slice = [r[idx] for idx in slice]
            topk.append(topk_slice)

        if return_scores:
            return scores, topk
        else:
            return topk

class AugmentedLLM:
    def __init__(self, metaprompt):
        self.metaprompt = metaprompt


    def __call__(self, queries, evidence, max_tokens = 1024, **kwargs):
        assert isinstance(queries, list)
        assert isinstance(evidence, list)
        assert len(queries) == len(evidence)

        # API does not support batching out of the box
        generations = []
        for i in range(len(queries)):
            query = queries[i]
            e = evidence[i]

            prompt = self.metaprompt + "".join([f"[{j}] " + e[j] + "\n" for j in range(len(e))]) + query + "\nAnswer:"
            print(f"About to call OpenAI Completion with prompt: {prompt}")
            out = openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                #model=model_path,
                model="gpt-3.5-turbo",
                max_tokens=max_tokens,
                **kwargs
            )
            """
            out = openai.Completion.create(model = model_path, 
                                           prompt = prompt, 
                                           max_tokens = max_tokens,
                                           temperature = 0,
                                           **kwargs)
            """
            generations.append(out.choices[0].message.content) # TODO can also return logprobs for eval
        return generations
    
    def logprob(self, queries, evidence, choices, **kwargs):
        # same as above, construct the prompt, loop through choices, get the log probability
        pass
        

class VectorDB:
    def __init__(self, key_path: str, value_path: str, device: str = "cuda"):
        self.device = device
        self.keys = torch.tensor(torch.load(key_path)).to(self.device).half()
        self.values = torch.load(value_path)
        # TODO add norm caching
        self.norms = torch.sqrt(torch.einsum("ij, ij -> i", self.keys, self.keys)) # for cosine similarity


    def topk_cosine(self, queries: torch.tensor, k: int, return_scores=False) -> torch.tensor:
        queries = queries.to(self.device)
        q_norms = torch.sqrt(torch.einsum("ij, ij -> i", queries, queries))
        prods = torch.einsum("ik, jk -> ij", queries, self.keys)
        norms = torch.einsum("i, j -> ij", q_norms, self.norms)
        
        sims = prods / (norms + 1e-5)
        scores, indices = torch.topk(sims, k, dim = -1)

        topk = []
        indices = indices.tolist()
        for slice in indices:
            topk_slice = [self.values[idx] for idx in slice]
            topk.append(topk_slice)

        if return_scores:
            return scores, topk
        else:
            return topk
        

def demo_input_loop(db, embedding_model, reranker_model, rag_llm, k = 5):
    queries = ["A 27-year-old male presents to urgent care complaining of pain with urination. He reports that the pain started 3 days ago. He has never experienced these symptoms before. He denies gross hematuria or pelvic pain. He is sexually active with his girlfriend, and they consistently use condoms. When asked about recent travel, he admits to recently returning from a boys’ trip” in Cancun where he had unprotected sex 1 night with a girl he met at a bar. The patients medical history includes type I diabetes that is controlled with an insulin pump. His mother has rheumatoid arthritis. The patients temperature is 99 F (37.2 C), blood pressure is 112/74 mmHg, and pulse is 81/min. On physical examination, there are no lesions of the penis or other body rashes. No costovertebral tenderness is appreciated. A urinalysis reveals no blood, glucose, ketones, or proteins but is positive for leukocyte esterase. A urine microscopic evaluation shows a moderate number of white blood cells but no casts or crystals. A urine culture is negative. Which of the following is the most likely cause for the patient’s symptoms? A: Chlamydia trachomatis, B: Systemic lupus erythematosus, C: Mycobacterium tuberculosis, D: Treponema pallidum"]
    print(f"Starting demo_input_loop")
    while len(queries) != 0:
        for q in queries:
            print(f"Query: {q} \n")

        print("*** Retrieving embedded queries... ***")
        print(f"Calling embedding_model with queries: {queries}")
        embedded_queries = embedding_model(queries)
        print(f"About to make retrievals from vector db with embedded_queries: {embedded_queries}")
        retrieved = db.topk_cosine(embedded_queries, k = 50) # hard coded
        
        for r in retrieved:
            for i in range(len(r)):
                print(f"Retrieved: [{i}] {r[i]} \n")

        print(f"*** Reranking... ***")

        reranked = reranker_model(queries, retrieved, k = k)

        for r in reranked:
            for i in range(len(r)):
                print(f"Reranked: [{i}] {r[i]} \n")

        print("*** Query Only ***")
        generations = rag_llm(queries, [[] for _ in range(len(queries))])
        for g in generations:
            print(f"Generation: {g} \n")
        
        print(f"*** Retrieval Only (k = {k})")
        generations = rag_llm(queries, [r[:k] for r in retrieved])
        for g in generations:
            print(f"Retreival only generation: {g} \n")

        print(f"*** Retrieval + Reranking (k = 50 -> k = {k}) ***")
        generations = rag_llm(queries, reranked)
        for g in generations:
            print(f"Retrieval + reranking generation: {g} \n")

        user_input = input("Another question? (ENTER to exit): ")
        queries.pop()
        if user_input.strip() != "":
            queries.append(user_input)
        else:
            print(f"Exiting")


class Task:
    def __init__(self, questions: list[str], answers: list[list[str]], labels: list[str], metaprompt: str):
        pass
        # construct prompts based on questions, answers, and metaprompt

    def evaluate(self, db, embedding_model, reranker_model, rag_llm, k = 5):
        pass
        # 1. construct endpoint for evaluation
        # 2. construct API prompt
        # TODO efficiency problem: 
        # 1. we will need to call the API 4 times without caching, one for each target. no open-ended generation.
        # 2. open-ended generation (limit # tokens), then check string matching. must be cheaper and more aligned to end use case.


def main():
    print("*** Loading vector database ***")
    db = VectorDB(
        key_path = key_path,
        value_path = value_path
    )

    print("*** Loading embedding model ***")
    embedding_model = EmbeddingModel(
        model_name_or_path = encoder_path,
        retrieval_instruction = ""
    )

    print("*** Loading reranker model ***")
    reranker_model = RerankerModel(
        model_name_or_path = "BAAI/bge-reranker-large"
    )

    rag_llm = AugmentedLLM(
        metaprompt = ""
    )
    
    demo_input_loop(db, 
        embedding_model=embedding_model, 
        reranker_model=reranker_model,
        rag_llm = rag_llm)

if __name__ == "__main__":
    main()
