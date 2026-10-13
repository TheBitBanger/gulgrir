# Configuration requirements

| ID    | Need                                                                                                                                                                                                 | Why |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| CFG-1 | An administrator needs to configure the instance with a few documented overrides, and to see at start-up what configuration is in effect, what is wrong with it, and what to change to fix it. Secrets never appear in any log. | Misconfiguration is the commonest self-hosting failure, and the audience shouldn't need to read code to find it. Logs get pasted into help requests and ingested by other tools, and a secret adds nothing to a diagnosis: the admin can read it in `.env`. |
