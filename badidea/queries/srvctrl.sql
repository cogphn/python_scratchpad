-- :name get_configs :many
select name from infra.configs;

-- :name get_config :one
SELECT args FROM infra.configs WHERE name = :name;

-- :name update_config :affected
UPDATE infra.configs
 SET args = :args
 WHERE name = :name;
