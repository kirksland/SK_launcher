# Board Scalability Target

Date: 2026-04-22

Cette doc fixe la cible de scalabilite du board. Le but n'est pas seulement d'avoir des fichiers plus petits: le but est que les zones qui vont grandir puissent grandir sans fragiliser le reste.

## Principe General

Tout ce qui est destine a etre extensible doit avoir:

- un contrat clair
- une source de verite explicite
- une validation
- un pipeline d'execution stable
- des tests de contrat

Autrement dit: on ne rend pas tout generique. On rend generiques les endroits qui sont censes accueillir de la croissance.

## Zones Qui Doivent Etre Scalable

### 1. Les Tools

Les tools sont le premier point d'extension produit.

La cible est:

```text
tools/board_tools/<tool_id>/
  tool.py
  image.py
  scene.py
```

Un tool doit pouvoir etre developpe a part, copie dans `tools/board_tools/`, puis decouvert automatiquement.

Contrats a garantir:

- `tool.py` declare un `EditToolSpec` valide
- `image.py` enregistre une fonction pure de transformation raster
- `scene.py` expose optionnellement un `SCENE_RUNTIME`
- le tool ne lit pas les attributs prives du board
- l'etat persistant du tool passe par la `tool_stack`

Amelioration prioritaire:

- ajouter une validation de registry qui remonte les tools invalides avec une erreur lisible
- ajouter des tests de contrat sur les specs et runtimes

### 2. Les Mutations Du Board

Les mutations sont toutes les actions qui changent la scene ou le board state:

- add media
- delete items
- move items
- scale items
- group / ungroup
- rename
- update tool stack
- commit override
- reorder tools

Aujourd'hui, ces mutations passent encore par plusieurs chemins. Pour scaler proprement, il faut un pipeline commun.

La cible:

```text
UI event
  -> BoardAction
  -> BoardMutationService
  -> scene/state mutation
  -> history/dirty/save/group refresh/preview
```

Un `BoardAction` doit decrire l'intention, pas seulement appeler une methode Qt.

Exemple:

```python
BoardAction(
    kind="move_items",
    payload={"item_ids": [...], "positions": {...}},
    history_label="Move items",
)
```

Le resultat attendu:

- toutes les mutations importantes passent par la meme voie
- undo/redo devient plus fiable
- autosave et dirty state sont coherents
- les drags/sliders peuvent etre groupes en une seule action

### 3. Le Preview Runtime

Les previews vont grandir avec les tools et les types de medias.

La cible:

```text
tool_stack + media source + preview settings
  -> preview request id/hash
  -> worker
  -> result
  -> apply only if still current
```

Contrats a garantir:

- un worker ne modifie jamais l'UI directement
- un resultat obsolete est ignore
- une preview peut etre remplacee par une plus recente
- les settings utilises pour calculer la preview sont hashables
- le cache depend au minimum du path, mtime, media kind et tool stack

Amelioration prioritaire:

- introduire un petit objet `PreviewRequest`
- centraliser le debounce/cancel/replace
- rendre le busy state visible et fiable

### 4. Le Board State

Le board state est la source persistante.

Sources de verite:

- `QGraphicsScene`: source temporaire pour le layout courant
- `board_state`: source persistante serialisable
- `BoardEditContext`: source temporaire du focus mode
- `tool_stack`: source persistante des edits non destructifs
- workers: jamais source de verite
- widgets UI: jamais source de verite durable

Contrats a garantir:

- save/load round-trip conserve les items, groupes et overrides
- les anciens payloads sont migres a l'entree
- les nouveaux payloads n'ecrivent plus d'anciens champs de compat
- un save vide ne peut pas ecraser un board existant sain
- les overrides sans media correspondant sont prunes

### 5. L'UI Board

L'UI doit etre scalable, mais pas devenir un framework dans le framework.

La cible:

- `BoardPage` compose les sections
- les widgets specialises vivent dans `ui/widgets`
- les panels tools sont decrits par les specs autant que possible
- les widgets emettent des signaux, les controleurs decident

Prochaine frontiere UI:

- extraire la construction du panneau edit en composants ou builder dedie
- eviter d'ajouter de nouvelles sections massives dans `BoardPage`

### 6. Commandes Et Raccourcis Globaux

Les raccourcis ne doivent pas etre un systeme board-only. Ils doivent passer par un systeme global de commandes d'application:

```text
shortcut
  -> command id
  -> app dispatcher
  -> domain dispatcher
  -> action metier
```

Le board declarera des commandes comme `board.layout.auto`, mais le meme systeme doit pouvoir gerer les projets, l'asset manager, le client sync, les settings et les futurs outils.

La cible detaillee vit dans `docs/app_commands_shortcuts_plan.md`.

## Ce Qui Ne Doit Pas Etre Trop Generique

Tout n'a pas besoin d'etre plugin-ready.

On peut garder simple:

- les items Qt de base
- le layout initial de `BoardPage`
- les helpers purs de groupes
- les workflows tres specifiques s'ils ne sont pas destines a etre etendus

La regle:

> Si une zone va recevoir plusieurs variantes dans le futur, elle merite un contrat. Sinon, elle merite surtout d'etre claire.

## Cible De Structure

```text
controllers/
  board_controller.py              Orchestration et facades publiques
  board_actions_controller.py      Dispatch actions/metiers board
  board_edit_*_controller.py       Mode edit specialise

core/
  board_actions/
    action.py                      Objet BoardAction / resultat
    mutations.py                   Mutations pures ou services
    history.py                     Strategie de groupage history

  board_state/
    payload.py
    overrides.py
    migrations.py                  Migrations de format explicites

  board_preview/
    request.py                     PreviewRequest, hash, stale checks
    runtime.py                     Queue/debounce/cancel

  commands/
    command.py                     AppCommand, CommandContext, CommandResult
    registry.py                    CommandRegistry globale
    shortcuts.py                   Bindings, overrides, conflits
    scopes.py                      Scopes connus et chevauchements

  board_edit/
    context.py
    tool_stack.py
    panels.py

tools/
  board_tools/<tool_id>/
```

Cette cible peut etre atteinte progressivement. Il ne faut pas tout creer d'un coup.

## Roadmap Proposee

### Etape 1. Contrats De Tools

Objectif:

- rendre le systeme de tools fiable pour de vrais ajouts futurs

Travail:

- ajouter un validateur de `EditToolSpec`
- valider unicite des ids
- valider `supports`, `default_for`, `ui_panel`, `ui_controls`
- valider que `SCENE_RUNTIME` respecte le contrat
- exposer des erreurs lisibles dans la registry
- tester un fake tool minimal

### Etape 2. Pipeline De Mutation

Objectif:

- arreter la multiplication des chemins qui changent scene/state/history

Travail:

- introduire `BoardAction`
- introduire une fonction/service `commit_board_action(...)`
- faire passer d'abord les mutations simples dedans: move, delete, group, rename
- ensuite les mutations edit: update stack, commit override

### Etape 3. Preview Runtime

Objectif:

- rendre les previews fluides et robustes quand les tools augmentent

Travail:

- creer `PreviewRequest`
- associer chaque worker a un id/hash
- ignorer les resultats obsoletes
- centraliser le debounce
- ajouter un etat busy/pending clair

### Etape 4. Board State Et Migrations

Objectif:

- rendre le format board stable dans le temps

Travail:

- ajouter une version de schema au payload
- isoler les migrations dans `core/board_state/migrations.py`
- tester les migrations de payload legacy vers schema courant
- documenter ce qui est garanti au save/load

### Etape 5. UI Edit Panel

Objectif:

- que l'ajout d'un tool ne demande pas de modifier `BoardPage`

Travail:

- rendre les panels plus generes depuis `ToolUiControlSpec`
- extraire un widget `BoardEditToolPanel`
- brancher les controls par metadata
- garder les tools scene libres d'ajouter une interaction scene, pas une UI custom fragile

## Definition De "Pro" Pour Ce Board

Le board sera vraiment pro quand:

- un nouveau tool peut etre ajoute sans toucher `BoardController`
- une mutation importante passe par un pipeline unique
- undo/redo reste fiable apres drag, scale, edit et group
- save/load round-trip est teste
- une preview lente ne peut pas ecraser une preview recente
- les payloads anciens sont migres explicitement
- l'UI reste fluide pendant pan/zoom/drag/preview
- les erreurs de plugin/tool sont lisibles et non bloquantes

## Position Actuelle

On est deja sur une bonne base:

- tools par dossier
- `BoardEditContext`
- `BoardToolSceneHost`
- `core.board_state`
- `core.board_scene`
- `core.board_actions` avec pipeline commun de mutation
- `core.board_preview.PreviewRequest` pour identifier les previews
- `core.board_preview.PreviewRuntimeState` pour active/pending/cancel des previews
- migrations explicites de payload board via `core.board_state.migrations`
- contrat save/load documente dans `docs/board_state_contract.md`
- commandes/raccourcis globaux via `core.commands`
- widgets board extraits
- chrome, controls actuels et preview stack du panneau edit extraits dans `ui.widgets.board_edit_panel`
- lecture/ecriture/visibilite des controls de tools pilotees par `ToolUiControlSpec`
- tests sur les briques pures

La prochaine marche n'est donc pas un gros refacto esthetique. La prochaine marche, c'est de continuer a connecter les surfaces encore manuelles aux contrats d'execution deja poses: groupage history des longues interactions, runtime preview plus centralise, migrations futures, et UI tool panels plus generes.
