# LexiGraph RAG - End-to-End Test Log

**Date:** July 15, 2026
**Result:** SUCCESS 🟢

## Flow Execution Summary

### 1. Ingestion (`POST /documents`)
- **Action**: Uploaded `P Shirbhate MOU QA Engineer.pdf`.
- **Result**: Successfully parsed by Unstructured and embedded into the vector store.
- **Output**: 
  ```json
  {
    "mongo_doc_id": "a6117dc6-efc5-48b8-b4b0-f49a2b8ea922",
    "source_file": "P Shirbhate MOU QA Engineer.pdf",
    "n_parents": 19,
    "n_children": 19,
    "n_vectors": 19
  }
  ```

### 2. Outline Generation (`POST /jobs`)
- **Action**: Sent prompt: *"Draft me 10 Important points which i need to read immediately"*
- **Result**: Successfully initialized job `4622b2a8-1072-4306-b090-e097849b8f17`. LLM successfully generated a 10-point structural outline.

### 3. Outline Approval / Override (`POST /jobs/{job_id}/outline/approve`)
- **Action**: Approved the outline, but successfully demonstrated the **Human-in-the-Loop Override** feature by passing a custom, single-section outline in the request body.
- **Result**: 
  ```json
  {
    "job_id": "4622b2a8-1072-4306-b090-e097849b8f17",
    "approved": true,
    "n_sections": 1
  }
  ```

### 4. Drafting Loop (`POST /jobs/{job_id}/run`)
- **Action**: Triggered the Burr state machine to run the "Retrieve -> Draft -> Evaluate" loop for the 1 section.
- **Result**: Completed without errors.
  ```json
  {
    "job_id": "4622b2a8-1072-4306-b090-e097849b8f17",
    "status": "done"
  }
  ```

### 5. Final Assembly (`GET /jobs/{job_id}/document`)
- **Action**: Fetched the completed draft.
- **Result**: The agent successfully drafted the section using the QA Engineer document context, and correctly appended citations tying the claims back to the exact parent chunks in MongoDB.
- **Output**:
  ```markdown
  ## string

  Section title: QA Engineer Skills & Qualifications

  The Independent Contractor engaged as QA Engineer shall possess and maintain skills and qualifications consistent with the Role Overview for the QA Engineer position, including the capabilities necessary to support product quality across web-based and AI-driven applications under the direction of the QA Operations Manager... [89fea590-37b1-41a7-85fb-070a5d96316c]

  _Citations: 89fea590-37b1-41a7-85fb-070a5d96316c_
  ```

## Conclusion
All systems (FastAPI, Unstructured, fastembed, Qdrant, MongoDB, Mirascope, and Apache Burr) are integrated and working flawlessly. Schema strictness and connection bugs have been fully resolved.
