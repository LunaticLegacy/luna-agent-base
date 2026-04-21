# Docs Index

This page is the English documentation index for Angelus.

## Overview

- [API Structure](./api_structure.md)
  - High-level description of the Flask API, routes, error handling, and runtime binding
- [Metadata Reference](./metadata_reference.md)
  - Metadata conventions for graph nodes, runtime state, agents, tools, and skills
- [Project Overview](./README.md)
  - English project homepage and quick start

## Backend

- [Backend API Map](./backend_api_map.md)
  - Backend dispatch flow, route responsibilities, and runtime execution mapping
- [Backend Reference](./backend_reference.md)
  - File-by-file reference for backend classes, functions, and methods
- [Backend Live Execution](./backend_live_execution.md)
  - Static graph snapshots, async run sessions, and SSE event streams

## Frontend

- [Frontend API Map](./frontend_api_map.md)
  - How the Angular frontend consumes backend APIs
- [Frontend Reference](./frontend_reference.md)
  - Behavior reference for components, services, templates, and styles
- [Frontend Receive Examples](./frontend_receive_examples.md)
  - Example payloads for rendering and debugging

## Structure

- [Agent Structure](./agent_structure.md)
  - Directory layout and swarm package conventions
- [Dynamic Graph Editing Protocol](./dynamic_graph_protocol.md)
  - Dynamic graph mutation mechanism, known issues, and fix priorities

## Suggested Reading Order

- If you want to see the API shape first, start with `api_structure.md`
- If you want to understand backend execution, start with `backend_api_map.md` and `backend_live_execution.md`
- If you want to understand frontend consumption, start with `frontend_api_map.md` and `frontend_reference.md`
- If you want to understand graph metadata, start with `metadata_reference.md`
- If you want to understand swarm packaging, start with `agent_structure.md`
