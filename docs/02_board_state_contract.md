# Board State Contract

Date: 2026-04-23

Cette doc decrit le contrat de sauvegarde/chargement du board. Le but est que le payload reste stable pendant que les tools, les previews et les interactions continuent d'evoluer.

## Source De Verite

Pendant l'edition, la scene Qt est la source temporaire du layout courant. Au moment d'une mutation board, le pipeline synchronise la scene vers un payload serialisable.

Sur disque, la source de verite est:

```text
<project>/.skyforge_board.json
```

Le payload sauvegarde:

- `schema_version`
- `items`
- `image_display_overrides`

Les widgets UI, les workers et les previews ne sont jamais des sources de verite durables.

## Schema Version

La version courante est:

```json
{
  "schema_version": 1
}
```

Tous les chargements passent par `core.board_state.migrations.migrate_board_payload`. Tous les saves passent aussi par la migration avant ecriture, afin que le fichier sur disque reste au format courant.

## Items

`items` est une liste de dictionnaires. Les types supportes sont:

- `image`
- `video`
- `sequence`
- `note`
- `group`

Les groupes referencent leurs membres par identifiants serialisables, pas par objets Qt.

## Overrides

Les overrides persistants vivent dans:

```json
{
  "image_display_overrides": {
    "plate.exr": {
      "tool_stack": []
    }
  }
}
```

La cle legacy `image_exr_display_overrides` est acceptee en entree et migree vers `image_display_overrides`.

Les nouveaux saves doivent rester centres sur `tool_stack`. Les anciens champs de compatibilite comme `brightness`, `contrast` ou `saturation` peuvent etre lus par les migrations/helpers, mais ne doivent pas redevenir le format de sauvegarde principal.

## Save

Le save board:

1. commit les overrides de focus courants si necessaire
2. synchronise les overrides avec les medias encore presents
3. migre le payload vers le schema courant
4. ecrit `.skyforge_board.json`
5. marque le board comme clean

Un save vide suspect est bloque si un payload existant contient des items, afin d'eviter d'ecraser un board sain pendant un chargement incomplet.

## Load

Le load board:

1. lit `.skyforge_board.json`
2. rejette les payloads non dictionnaires ou invalides
3. migre le payload vers le schema courant
4. reconstruit les items Qt depuis `items`
5. reapplique les overrides
6. reset l'history sur l'etat applique

Les migrations doivent etre pures, testees, et ne doivent pas dependre de Qt.
