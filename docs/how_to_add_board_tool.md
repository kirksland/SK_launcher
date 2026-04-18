# Ajouter Un Tool De Board

Date: 2026-04-18

## Le point important

Il y a **deux couches differentes** dans le systeme de tools:

- `tools/edit_tools/`
  - decrit un tool pour le board edit
  - sert a l'UI, a la stack, a la normalisation, aux defaults, a l'ordre et au support media
- `tools/image_tools/`
  - applique concretement un effet raster sur une image preview
  - sert au rendu image pendant les previews ou exports image

En bref:

- `edit_tools` = "definition produit / UX / state"
- `image_tools` = "execution pixel"

## Pourquoi on a les deux

Un tool du board n'est pas forcement un simple filtre image.

Exemples:

- `bcs`
  - a une UI avec 3 sliders
  - a un etat dans la `tool_stack`
  - a aussi un rendu pixel sur les previews image
- `vibrance`
  - meme logique
- `crop`
  - a une UI
  - a un etat dans la `tool_stack`
  - a une interaction de scene
  - mais **n'est pas** un filtre raster `image_tools`

Donc:

- si ton tool existe dans le board edit, il lui faut une spec `edit_tools`
- s'il doit transformer des pixels RGB, il lui faut en plus un module `image_tools`
- s'il manipule la scene au lieu des pixels, il peut avoir une spec `edit_tools` sans `image_tools`

## Vue simple du flux

### 1. Definition du tool

Le tool est decouvert via:

- `tools/edit_tools/registry.py`

Chaque tool enregistre une `EditToolSpec` dans un dossier:

- `tools/edit_tools/<tool_id>/tool.py`

La spec dit:

- quel est son `id`
- sur quels medias il marche (`supports`)
- son etat par defaut
- comment normaliser son etat
- comment savoir s'il est actif
- quel panneau UI afficher
- quels controles UI il expose

### 2. Integration dans le board

Le board:

- liste les tools disponibles selon `supports`
- lit la spec via `get_edit_tool(...)`
- construit/synchronise les panels via `core/board_edit/panels.py`
- stocke le state dans la `tool_stack`

### 3. Rendu effectif

Selon le type de tool:

- soit le rendu passe par `tools/image_tools/registry.py` puis `apply_image_tool_stack(...)`
- soit le comportement passe par un runtime ou une interaction de scene
  - exemple: `core/board_edit/crop_scene.py`

## Quand creer quoi

### Cas A. Tool purement declaratif / logique board

Exemple:

- un toggle metadata
- un offset de timing
- un crop de scene

A faire:

- `tools/edit_tools/<tool_id>/tool.py`

Pas necessaire:

- `tools/image_tools/<tool_id>.py`

### Cas B. Tool de reglage image avec preview raster

Exemple:

- exposure
- hue shift
- gamma

A faire:

- `tools/edit_tools/<tool_id>/tool.py`
- `tools/image_tools/<tool_id>.py`

### Cas C. Tool interactif de scene

Exemple:

- crop avec handles
- perspective handles
- region mask editable dans la vue

A faire:

- `tools/edit_tools/<tool_id>/tool.py`
- un module runtime/scene dedie dans `core/board_edit/*` ou `core/board_scene/*`

Pas forcement necessaire:

- `tools/image_tools/<tool_id>.py`

## Anatomie d'un `edit_tool`

Exemple:

- `tools/edit_tools/bcs/tool.py`

Une spec contient surtout:

- `id`
- `label`
- `supports`
- `default_state_factory`
- `normalize_state_fn`
- `is_effective_fn`
- `order`
- `stack_insert_at`
- `ui_panel`
- `ui_settings_keys`
- `ui_controls`

### Role des champs

- `supports`
  - determine si le tool est dispo pour `image`, `video`, `sequence`, etc.
- `default_state_factory`
  - construit l'etat par defaut
- `normalize_state_fn`
  - garantit un state propre et borné
- `is_effective_fn`
  - dit si le tool a un vrai effet ou s'il est a son etat neutre
- `stack_insert_at`
  - permet de choisir une position preferentielle dans la `tool_stack`
- `ui_panel`
  - nom du panel UI associe
- `ui_settings_keys`
  - cles attendues pour l'etat UI
- `ui_controls`
  - description declarative des sliders/controles

## Anatomie d'un `image_tool`

Exemple:

- `tools/image_tools/bcs.py`

Le pattern est simple:

1. tu crees une fonction `apply_fn(rgb, settings)`
2. tu enregistres le tool avec `register_tool("<tool_id>", apply_fn)`

Contraintes pratiques:

- l'input est un RGB array
- le tool doit etre tolerant aux erreurs
- il doit retourner un array image compatible
- le `tool_id` doit matcher la spec `edit_tools`

## Recette: ajouter un nouveau tool image

Exemple: `exposure`

### 1. Creer la spec board edit

Chemin:

- `tools/edit_tools/exposure/tool.py`

Tu y definis:

- `id="exposure"`
- `supports=("image",)`
- un state du style `{"amount": 0.0}`
- une normalisation
- `ui_panel="exposure"`
- `ui_settings_keys=("amount",)`
- un `ToolUiControlSpec("amount", "Exposure", -2.0, 2.0, ...)`

### 2. Enregistrer la spec

Dans ce meme fichier:

- `register_edit_tool(EditToolSpec(...))`

### 3. Ajouter le rendu raster

Chemin:

- `tools/image_tools/exposure.py`

Tu y definis:

- `_apply_exposure(rgb, settings)`
- `register_tool("exposure", _apply_exposure)`

### 4. Verifier que le tool apparait

Le board decouvre automatiquement:

- les specs `tools/edit_tools/*/tool.py`
- les renderers `tools/image_tools/*.py`

Donc normalement il n'y a rien d'autre a brancher si ton tool suit le contrat existant.

## Recette: ajouter un tool interactif

Exemple: un tool `mask_box`

### 1. Faire la spec `edit_tools`

Elle decrit:

- l'etat
- les defaults
- la normalisation
- les sliders ou champs eventuels

### 2. Faire un module runtime/scene

Exemple de cible:

- `core/board_edit/mask_box_scene.py`

Il portera:

- hit test
- drag state
- creation d'overlays
- calcul des nouvelles valeurs

### 3. Garder `BoardController` en orchestrateur

Le controller ne devrait faire que:

- appeler le runtime de scene
- propager l'etat vers la `tool_stack`
- commit les overrides / previews si necessaire

## Regle pratique pour ne pas se perdre

Pose-toi juste cette question:

> Est-ce que je suis en train de decrire un tool pour le board, ou d'executer un effet sur des pixels ?

Si tu decris:

- `tools/edit_tools`

Si tu executes un rendu image:

- `tools/image_tools`

Si tu pilotes la scene/interactions:

- `core/board_edit` ou `core/board_scene`

## Structure recommandee pour un nouveau tool

Pour un tool complet `exposure`:

```text
tools/
  edit_tools/
    exposure/
      __init__.py
      tool.py
  image_tools/
    exposure.py
tests/
  test_board_edit_panels.py
  test_board_tool_stack.py
```

Pour un tool interactif sans rendu raster:

```text
tools/
  edit_tools/
    crop_like_tool/
      __init__.py
      tool.py
core/
  board_edit/
    crop_like_tool_scene.py
```

## Fichiers a regarder comme exemples

- `tools/edit_tools/bcs/tool.py`
- `tools/edit_tools/vibrance/tool.py`
- `tools/edit_tools/crop/tool.py`
- `tools/image_tools/bcs.py`
- `tools/image_tools/vibrance.py`
- `core/board_edit/panels.py`
- `core/board_edit/crop_scene.py`

## Conclusion simple

Le systeme n'est pas "double" pour rien.

Il separe volontairement:

- la description d'un tool dans le board
- l'execution technique de son rendu

C'est justement ce qui permet d'avoir:

- des tools purement UI/state
- des tools raster
- des tools interactifs de scene

sans tout remelanger dans `BoardController`.
