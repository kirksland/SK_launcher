# Ajouter Un Tool De Board

Date: 2026-04-18

## Idee simple

La cible maintenant, c'est:

- un tool = un dossier
- ce dossier porte ses capacites optionnelles

Concretement:

```text
tools/
  board_tools/
    <tool_id>/
      tool.py
      image.py
      scene.py
```

Tous les fichiers ne sont pas obligatoires:

- `tool.py`
  - spec board/edit
  - UI
  - defaults
  - normalisation
  - support media
- `image.py`
  - rendu raster sur preview/export image
- `scene.py`
  - interaction de scene
  - handles
  - hit test
  - drag

## Pourquoi on fait ca

Avant, un tool complet pouvait etre disperse entre:

- `tools/edit_tools/`
- `tools/image_tools/`
- parfois `core/board_edit/`

La separation etait saine pour sortir du monolithe, mais pas tres agreable a maintenir.

La vraie organisation a viser est:

- `tools/board_tools/<tool_id>/...`

## Les trois couches a bien distinguer

### 1. `tool.py`

C'est la definition du tool dans le board.

Il dit:

- son `id`
- son `label`
- sur quels medias il marche
- son etat par defaut
- comment normaliser cet etat
- comment savoir s'il est actif
- quel panel UI il expose
- quels sliders/controles il decrit

Exemple:

- `tools/board_tools/bcs/tool.py`
- `tools/board_tools/crop/tool.py`

### 2. `image.py`

C'est l'execution pixel.

Il prend:

- une image RGB
- des `settings`

et retourne une image transformee.

Exemple:

- `tools/board_tools/bcs/image.py`
- `tools/board_tools/vibrance/image.py`

### 3. `scene.py`

C'est l'interaction dans la scene.

Il gere par exemple:

- les handles
- les overlays
- le drag
- le hit test

Exemple:

- `tools/board_tools/crop/scene.py`

## Quand creer quoi

### Cas A. Tool de board simple

Exemple:

- metadata toggle
- offset logique
- parametre stocke dans la `tool_stack`

A faire:

- `tools/board_tools/<tool_id>/tool.py`

### Cas B. Tool image

Exemple:

- exposure
- hue shift
- gamma
- sharpen

A faire:

- `tools/board_tools/<tool_id>/tool.py`
- `tools/board_tools/<tool_id>/image.py`

### Cas C. Tool interactif de scene

Exemple:

- crop
- perspective box
- region mask

A faire:

- `tools/board_tools/<tool_id>/tool.py`
- `tools/board_tools/<tool_id>/scene.py`

### Cas D. Tool complet

Exemple:

- un tool avec UI + rendu image + interaction scene

A faire:

- `tools/board_tools/<tool_id>/tool.py`
- `tools/board_tools/<tool_id>/image.py`
- `tools/board_tools/<tool_id>/scene.py`

## Comment ca se branche

### Discovery edit

La couche edit est maintenant:

- `tools/board_tools/edit.py`

decouvre maintenant:

- les anciens tools `tools/edit_tools/*`
- les nouveaux tools `tools/board_tools/*/tool.py`

### Discovery image

La couche image est maintenant:

- `tools/board_tools/image.py`

decouvre maintenant:

- les anciens modules `tools/image_tools/*.py`
- les nouveaux modules `tools/board_tools/*/image.py`

Donc on peut migrer progressivement sans casser l'app.

### Discovery unifiee

On a maintenant aussi une registry source de verite:

- `tools/board_tools/registry.py`

Elle expose les capacites d'un tool:

- `has_tool`
- `has_image`
- `has_scene`

Le but est que le board puisse raisonner a terme sur des capacites explicites, pas juste sur des conventions de fichiers implicites.

Pour les tools interactifs, la couche `scene.py` peut maintenant exposer un runtime formel:

- `SCENE_RUNTIME`

Ce runtime suit un contrat explicite via:

- `tools/board_tools/base.py`
- `BoardToolSceneRuntime`

Les hooks attendus sont:

- `refresh_handles`
- `clear_handles`
- `panel_value_changed`
- `mouse_press`
- `mouse_move`
- `mouse_release`
- optionnellement `apply_to_focus_item`

## Ce qu'il reste en compatibilite

L'ancienne separation `tools/edit_tools` / `tools/image_tools` a maintenant ete retiree du code actif.

Pareil pour:

- `core/board_edit/crop_scene.py`

qui reste comme point d'entree stable, tout en reexportant maintenant:

- `tools/board_tools/crop/scene.py`

## Recette: creer un nouveau tool image

Exemple: `exposure`

Structure recommandee:

```text
tools/
  board_tools/
    exposure/
      __init__.py
      tool.py
      image.py
```

### `tool.py`

Tu definis:

- `id="exposure"`
- `supports=("image",)`
- un state par defaut
- une normalisation
- un `ui_panel`
- des `ui_controls`

Puis tu fais:

- `register_edit_tool(EditToolSpec(...))`

### `image.py`

Tu definis:

- `_apply_exposure(rgb, settings)`

Puis:

- `register_tool("exposure", _apply_exposure)`

## Recette: creer un tool interactif

Exemple: `mask_box`

Structure recommandee:

```text
tools/
  board_tools/
    mask_box/
      __init__.py
      tool.py
      scene.py
```

### `tool.py`

Decrit:

- les settings
- les defaults
- la normalisation
- les controles UI

### `scene.py`

Porte:

- les handles
- l'etat de drag
- la creation des overlays
- le calcul des nouvelles valeurs

Le `BoardController` ne devrait faire que:

- appeler ce runtime
- remettre a jour la `tool_stack`
- commit preview/override si besoin

## Regle mentale utile

Pose-toi juste cette question:

> Est-ce que je suis en train de definir le tool, de transformer des pixels, ou de piloter la scene ?

La reponse donne directement le fichier:

- definition du tool -> `tool.py`
- rendu image -> `image.py`
- interaction scene -> `scene.py`

## Exemples actuels

- `tools/board_tools/edit.py`
- `tools/board_tools/image.py`
- `tools/board_tools/bcs/tool.py`
- `tools/board_tools/bcs/image.py`
- `tools/board_tools/vibrance/tool.py`
- `tools/board_tools/vibrance/image.py`
- `tools/board_tools/crop/tool.py`
- `tools/board_tools/crop/scene.py`

## Conclusion

La structure qu'on vise n'est plus:

- un systeme par dossier technique global

mais:

- un systeme par tool

avec des capacites optionnelles regroupees ensemble.

C'est beaucoup plus plug & play, beaucoup plus lisible, et plus naturel pour faire evoluer le board dans le temps.
