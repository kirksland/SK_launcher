# Board Architecture Overview

Date: 2026-04-22

Cette doc decrit la structure actuelle du board: qui possede quoi, comment les flux principaux circulent, et ou ajouter de nouvelles capacites.

## Role Du Board

Le board est une scene 2D persistante qui permet de:

- poser des medias: images, videos, sequences, notes
- organiser ces medias en groupes
- sauvegarder et recharger l'etat de la scene
- ouvrir un media en focus mode
- appliquer des edits non destructifs via une stack de tools
- generer des previews image, video, EXR et sequence
- exporter certains resultats, par exemple un segment video vers une sequence

Le board n'est donc pas seulement une page UI. C'est un petit sous-systeme compose d'une scene Qt, d'un etat serialise, d'un mode edit, d'une registry de tools et de workers media.

## Carte Des Modules

```text
ui/
  pages/board_page.py              Composition UI principale du board
  widgets/board_view.py            Vue graphique, pan/zoom, selection, drop
  widgets/board_timeline.py        Timeline video/sequence
  widgets/board_groups_tree.py     Widget tree des groupes
  widgets/board_tool_stack_row.py  Ligne visuelle d'une entree de stack

controllers/
  board_controller.py              Orchestrateur haut niveau
  board_edit_*_controller.py       Sous-controleurs du mode edit
  board_groups_controller.py       Synchronisation panneau groupes
  board_group_actions_controller.py Actions groupes
  board_scene_view_controller.py   Vue, scene, workspace
  board_media_*_controller.py      Import/rendu media
  board_history_controller.py      Undo/redo et historique
  board_legacy_payload_controller.py Build/apply payload historique

core/
  board_scene/                     Items Qt et helpers de groupes
  board_state/                     Payload, overrides, rebuild, apply
  board_edit/                      Session edit, stack, panels, workers, runtime
  board_io.py                      Lecture/ecriture du fichier board
  board_media_cache.py             Cache pixmap/thumbnails
  board_apply_runtime.py           Application progressive du payload

tools/
  board_tools/                     Registry et implementations des tools
```

## Responsabilites Principales

### `BoardController`

`controllers/board_controller.py` reste le point d'entree principal. Il:

- instancie les sous-controleurs
- connecte les signaux Qt de `BoardPage`
- maintient l'etat global courant: projet, scene, dirty flag, cache, focus item, workers actifs
- orchestre sauvegarde, chargement, import, suppression, focus mode et historique
- expose des facades publiques pour les sous-controleurs, par exemple `edit_context`, `current_edit_tool_stack()` ou `prepare_edit_tools_for_kind()`

La direction actuelle est de garder `BoardController` comme chef d'orchestre, pas comme lieu de logique metier detaillee.

### `BoardPage`

`ui/pages/board_page.py` construit les widgets Qt:

- `BoardPage`: layout general, panneau edit, preview, controls, signals
- `BoardView`: vue graphique extraite dans `ui/widgets/board_view.py`
- `BoardTimeline`: timeline interactive extraite dans `ui/widgets/board_timeline.py`

`BoardPage` doit rester aussi passif que possible: il expose des setters/getters UI et des signaux, mais il ne decide pas des workflows metier.

Widgets deja extraits:

- `BoardGroupsTree`
- `BoardToolStackRow`
- `BoardTimeline`
- `BoardView`

### `core.board_scene`

`core/board_scene/items.py` contient les items graphiques:

- `BoardImageItem`
- `BoardVideoItem`
- `BoardSequenceItem`
- `BoardNoteItem`
- `BoardGroupItem`

Ces classes savent se dessiner, porter quelques donnees Qt, exposer leur path, et recevoir des overrides visuels comme un pixmap preview ou un crop.

`core/board_scene/groups.py` contient les regles pures autour des groupes:

- association item/groupe
- selection ciblee depuis le tree
- serialisation des membres
- regles de context menu
- renommage et filtrage des items groupables

### `core.board_state`

`core/board_state` est la couche payload et persistence logique:

- `payload.py`: clone, normalisation, parsing des overrides
- `apply.py`: application progressive d'un payload dans la scene
- `rebuild.py`: reconstruction des items depuis les entries sauvegardees
- `overrides.py`: creation, commit, application et reapplication des overrides image/video

Le payload sauvegarde l'etat du board. Les edits non destructifs sont stockes principalement sous forme de `tool_stack` dans les overrides.

### `core.board_edit`

`core/board_edit` porte le mode edit:

- `session.py`: etat de session et conversion override -> stack
- `context.py`: facade partagee entre les controleurs edit
- `tool_stack.py`: operations pures sur la stack de tools
- `panels.py`: mapping entre tool specs, panels UI et etats de panel
- `handles.py`: primitives d'interaction crop
- `media_runtime.py`: timers playback video/sequence
- `workers.py`: workers Qt pour EXR, previews image, video->sequence, export segment

Le point central recent est `BoardEditContext`. Il evite aux sous-controleurs de lire/ecrire directement les champs prives du `BoardController` pour:

- le type de media en focus (`focus_kind`)
- la stack de tools active
- l'index selectionne dans la stack
- les definitions UI disponibles pour ce media

## Sous-Controleurs Du Mode Edit

Le mode edit est decoupe en plusieurs controleurs specialises.

### `BoardEditPanelController`

Ouvre et configure le panneau edit selon le media:

- image
- EXR
- video
- sequence

Il prepare aussi la stack de tools via `BoardController.prepare_edit_tools_for_kind(...)`.

### `BoardEditToolsController`

Possede la logique de tools editable:

- discovery des tools
- stack par defaut
- ajout, suppression, reorder
- normalisation d'une entree
- synchro stack -> UI
- lecture/ecriture des panels
- evaluation de l'efficacite d'une stack

C'est le controleur qui fait le pont entre `BoardEditContext`, `BoardPage` et les specs dans `tools/board_tools`.

### `BoardEditPreviewController`

Gere les previews:

- scheduling debounce pendant les sliders
- preview EXR channel
- preview image adjust
- preview appliquee directement sur l'item focus
- workers de preview par item dans la scene

Il ne devrait pas decider de la structure des tools; il consomme la stack courante via `current_edit_tool_stack()`.

### `BoardEditFocusController`

Gere l'entree/sortie du focus mode:

- isolation visuelle de l'item focus
- overlay
- reset de session edit
- hooks des tools interactifs de scene
- host expose aux tools de scene via `BoardToolSceneHost`

C'est lui qui permet a un tool comme `crop` de manipuler la scene sans connaitre les attributs prives du board.

### `BoardEditTimelineController`

Gere la timeline video/sequence:

- playhead
- scrubbing
- playback timer
- split/export clip
- preview du frame courant en focus

Il lit maintenant le type de focus via `BoardEditContext`.

## Systeme De Tools

La structure cible est:

```text
tools/board_tools/<tool_id>/
  __init__.py
  tool.py    # definition edit/UI/defaults
  image.py   # rendu pixel optionnel
  scene.py   # interaction scene optionnelle
```

Exemples actuels:

- `bcs`: `tool.py` + `image.py`
- `vibrance`: `tool.py` + `image.py`
- `crop`: `tool.py` + `scene.py`

### Discovery

La discovery se fait par:

- `tools/board_tools/edit.py` pour les specs edit
- `tools/board_tools/image.py` pour les transforms raster
- `tools/board_tools/registry.py` pour les capacites globales d'un tool

`BoardToolCapabilities` indique si un tool possede:

- une definition edit
- une implementation image
- une implementation scene

### Tool Stack

Une stack est une liste d'entrees normalisees:

```python
{
    "id": "bcs",
    "enabled": True,
    "settings": {
        "brightness": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
    },
}
```

La stack est la source de verite pour les edits non destructifs. Les anciens champs scalaires ne doivent pas redevenir le modele principal.

### Tool Scene Runtime

Un tool interactif peut exposer `SCENE_RUNTIME` via `BoardToolSceneRuntime`.

Le runtime recoit un host type par `BoardToolSceneHost`, avec des operations stables:

- lire l'item focus
- lire/ecrire l'etat du panel
- ecrire l'etat dans la stack
- stocker un etat scene temporaire par tool
- commit l'override courant
- scheduler une preview
- rafraichir le workspace

Cette frontiere est importante: un `scene.py` de tool ne doit pas piocher dans `BoardController`.

## Flux Principaux

### Chargement Du Board

1. `BoardController.set_project(...)` definit le projet actif.
2. `load_board()` lit le payload via `core.board_io`.
3. `BoardApplyRuntime` applique le payload progressivement.
4. `core.board_state.rebuild` reconstruit les items.
5. `core.board_state.apply` rattache les groupes.
6. Les overrides sont reappliques via `core.board_state.overrides`.
7. La scene, le tree de groupes et l'historique sont synchronises.

### Sauvegarde

1. Le controller synchronise l'etat scene -> payload.
2. Les overrides courants sont injectes dans le board state.
3. `core.board_io.save_board_payload(...)` ecrit le fichier board.
4. L'historique peut reconstruire un payload via `BoardLegacyPayloadController`.

### Ouverture En Focus Mode

1. L'utilisateur ouvre une image/video/sequence.
2. `BoardEditPanelController` configure le panel adapte.
3. `BoardEditContext` recoit le `focus_kind`.
4. `BoardEditToolsController` prepare la stack depuis l'override existant ou les defaults.
5. `BoardEditFocusController` isole l'item et branche les interactions scene.
6. Les previews sont gerees par `BoardEditPreviewController` ou la timeline.

### Changement D'un Slider De Tool

1. `BoardPage` emet un signal Qt.
2. `BoardEditToolsController` lit le panel state.
3. La stack est mise a jour dans `BoardEditContext`.
4. Si le tool a une interaction scene, le runtime scene est appele.
5. Sinon, une preview image/video est schedulee.
6. L'override est commit si necessaire.

### Preview Image / EXR

1. `BoardEditPreviewController` debounce les modifications.
2. Un worker est cree:
   - `ExrChannelPreviewWorker`
   - `ImageAdjustPreviewWorker`
3. Le worker applique la stack de tools si necessaire.
4. Le resultat revient au thread UI.
5. L'item focus recoit un pixmap override ou le panneau preview affiche le rendu.
6. `core.board_state.overrides` met a jour l'override persistent.

### Tool Interactif De Scene

Exemple: crop.

1. Le tool expose `SCENE_RUNTIME`.
2. Le focus controller recupere le runtime via `tools.board_tools.registry`.
3. Les events souris de la scene sont routes vers le runtime.
4. Le runtime manipule uniquement le `BoardToolSceneHost`.
5. Les settings sont renvoyes dans la stack.
6. L'item focus est mis a jour et l'override est commit.

## Regles D'Architecture

### Ce Que `BoardController` Peut Faire

- orchestrer les sous-systemes
- exposer des facades publiques stables
- connecter les signaux de haut niveau
- coordonner scene, payload, edit, historique

### Ce Que `BoardController` Devrait Eviter

- connaitre les details internes d'un tool precis
- parser manuellement la stack de tools
- gerer directement les widgets de chaque panel
- contenir de nouvelles classes UI ou scene
- accumuler de nouveaux workflows media longs

### Ce Qu'un Tool Peut Faire

- declarer ses settings et defaults dans `tool.py`
- appliquer un rendu raster dans `image.py`
- piloter une interaction scene dans `scene.py`
- utiliser le host stable fourni par le board

### Ce Qu'un Tool Ne Devrait Pas Faire

- importer `BoardController`
- lire des attributs prives du board
- dependre d'un widget Qt precis dans `BoardPage`
- sauvegarder son etat ailleurs que dans la stack ou dans un override dedie par le host

## Etat Actuel Et Dette Restante

La structure est deja bien separee:

- les items scene sont sortis de `BoardController`
- le state/payload est dans `core.board_state`
- les tools vivent par dossier dans `tools/board_tools/<tool_id>`
- le mode edit est decoupe en controleurs specialises
- `BoardEditContext` centralise l'etat edit partage
- le contrat des tools interactifs est formalise par `BoardToolSceneHost`

Dette restante prioritaire:

- `ui/pages/board_page.py` a ete nettement reduit, mais `BoardPage` reste encore dense: la prochaine dette UI est plutot la construction du panneau edit et des sous-sections internes.
- `BoardController` garde des wrappers prives de compat. Ils sont de moins en moins utilises hors du controller, mais peuvent etre retires par petites passes.
- `BoardLegacyPayloadController` porte encore un nom historique. Avant de le renommer ou le supprimer, il faut verifier son role exact dans l'historique et le format sauvegarde.
- Les panels UI des tools sont encore partiellement lies a des widgets existants. La direction propre est de continuer vers des panels pilotes par specs.

## Direction De Refacto

Ordre recommande:

1. Remplacer progressivement les appels internes `_...` de `BoardController` par des facades publiques ou par les sous-controleurs.
2. Continuer a rendre les panels tools plus metadata-driven.
3. Extraire les grandes sous-sections de construction UI restantes dans `BoardPage`.
4. Auditer `BoardLegacyPayloadController` pour clarifier s'il s'agit d'un vrai legacy ou d'un serializer d'historique a renommer.

La cible reste simple: un board compose de briques claires, ou les tools peuvent etre developpes dans leur dossier puis ajoutes au board sans modifier le coeur.
