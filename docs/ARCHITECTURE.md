# Architecture

EldanaMapping is deliberately small at the edge and expressive in the product layer.

## Current shape

```text
Browser UI (web/)
    ├── semantic HTML sections
    ├── CSS design system
    └── app.js state + map interactions
Local HTTP server (app/server.py)
    └── serves the frontend with zero runtime dependencies
```

The first milestone keeps the demo portable. The domain model is represented in `web/app.js` while the server remains an uncomplicated seam for adding JSON endpoints, persistence, and authentication.

## Design principles

1. Make the first interaction understandable in under ten seconds.
2. Keep community language human and specific.
3. Let the interface feel like a notebook, not an operations console.
4. Prefer small, composable modules over a framework-shaped monolith.
