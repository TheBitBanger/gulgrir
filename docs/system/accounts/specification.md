# Accounts specification

| ID     | Behavior                                                                                                                                 | Verified by |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| ACC-S1 | When no superuser exists at start-up, one is created from `GULGRIR_ADMIN_USER` and `GULGRIR_ADMIN_PASSWORD`. If either is missing, start-up stops with a message that no superuser exists and naming the missing variables. When a superuser exists, both are ignored. | code test |
