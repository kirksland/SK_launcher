
## Ce que fait aujourd'hui le board

Le board sert a la fois de:

- scene 2D libre avec items image/video/sequence/note/groupe
- navigateur d'assets de board
- mini-editeur non destructif pour image/video/sequence
- point d'entree pour conversion media et manipulations de scene

Cette richesse explique pourquoi `controllers/board_controller.py` reste massif: il ne gere pas seulement "un controller UI", il porte aussi des modeles de scene, des workflows media, et la logique du mode edit.

## Refacto deja en place

Le dernier gros refacto a pose les bonnes briques:

- `core/board_edit/session.py`
  - etat de session d'edition
- `core/board_edit/tool_stack.py`
  - creation, normalisation et mise a jour d'une stack d'outils
- `core/board_edit/handles.py`
  - logique des handles de crop
- `core/board_edit/media_runtime.py`
  - runtime de playback image sequence / video
- `tools/board_tools/<tool_id>/tool.py`
  - declaration des outils editables via `EditToolSpec`
- `tools/board_tools/<tool_id>/image.py`
  - application concrete de certains effets sur les previews raster

Conclusion: on n'est plus dans un board monolithique pur. On est dans une architecture de transition deja modularisee, mais pas encore totalement decouplee.

## Frontieres actuelles

### Ce qui est bien separe

- les specs d'outils (`id`, label, supports, defaults, normalisation, `is_effective`)
- la registry des edit tools
- la stack d'outils comme structure de donnees
- le runtime de lecture video/sequence
- une partie de la logique de preview image

### Ce qui reste encore trop dans `BoardController`

- les classes d'items de scene:
  - `BoardImageItem`
  - `BoardVideoItem`
  - `BoardSequenceItem`
  - `BoardNoteItem`
  - `BoardGroupItem`
- le wiring UI complet de la page board
- la coordination scene <-> arbre des groupes
- la synchronisation session edit <-> widgets Qt
- les decisions d'affichage des panneaux d'outils
- une partie des workflows media annexes

## Le point cle sur les tools edit

La confusion vient de la difference entre:

- "les tools sont declares independamment"
- et "le mode edit est entierement pilote par ces tools"

Aujourd'hui, les tools sont declares independamment dans `tools/board_tools/<tool_id>/`.
Mais le mode edit n'est pas encore 100% pilote par metadata. Le controller sait encore:

- quel tool affiche quels widgets
- comment lire certaines valeurs de la stack pour les remettre dans l'UI
- comment rebrancher certaines valeurs sur l'item focalise

Autrement dit:

- les tools sont modularises
- l'UI d'edition ne l'est pas encore totalement

## Dette residuelle identifiee

### 1. `BoardController` melange encore trop de couches

Aujourd'hui il contient:

- des `QGraphicsItem`
- des handlers d'events de vue
- des actions media
- des operations de persistence
- de la logique d'edition

C'est le plus gros point de dette restant.

### 2. L'UI edit reste partiellement hardcodee

Le controller continue d'avoir des decisions explicites du type:

- afficher les controles BCS
- afficher le slider vibrance
- afficher le panneau crop

Cela fonctionne, mais ce n'est pas encore un vrai systeme de panneaux drive par spec.

### 3. La session d'edition reste orientee "tools connus"

`EditSessionState` garde encore des champs dedies:

- brightness
- contrast
- saturation
- vibrance
- crop

Ce n'est pas faux pour un systeme en transition, mais ce n'est pas la cible finale si on veut un mode edit reellement generique.

### 4. Les items de scene vivent encore dans le controller

Meme si ce n'est pas le probleme le plus urgent, sortir les items vers un module `board_scene` ou `board_items` allegerait fortement le fichier.

## Cible d'architecture

La cible propre serait:

- `ui/pages/board_page.py`
  - widgets purs
- `controllers/board_controller.py`
  - orchestration haut niveau seulement
- `core/board_scene/*`
  - items de scene, selection, groupes, interactions de scene
- `core/board_edit/*`
  - session edit, mapping stack <-> UI state, preview policies, crop handles
- `tools/board_tools/<tool_id>/tool.py`
  - spec des outils editables
- `tools/board_tools/<tool_id>/image.py`
  - application raster des outils qui ont un rendu preview
- `tools/board_tools/<tool_id>/scene.py`
  - interaction de scene pour les tools interactifs

Le point important est que `BoardController` devrait devenir un chef d'orchestre, pas le depot central de toute la logique.

## Ordre de refacto recommande

### Etape 1. Continuer a sortir la logique de stack hors du controller

Objectif:

- eviter que `BoardController` connaisse trop le schema interne des outils

Travail:

- centraliser extraction/normalisation/effective-state dans `core/board_edit/tool_stack.py`
- reduire les branches locales special-case quand elles ne servent qu'a interpreter la stack

Statut: termine le 2026-04-18

Ce qui a ete sorti de `BoardController`:

- extraction d'etats BCS / crop / vibrance depuis la stack
- evaluation de l'efficacite d'une stack
- conversion des anciens overrides vers une `tool_stack`
- valeurs visuelles derivees de la stack via `EditVisualState`

### Etape 2. Introduire des panneaux d'outils pilotables par spec

Objectif:

- ne plus coder l'UI edit autour de `crop`, `vibrance`, `bcs` en dur

Travail:

- definir une forme de "tool panel definition"
- permettre a un tool de decrire ses controles
- laisser le controller juste monter/dispatcher ces controles

Statut: termine le 2026-04-18

Premier pas deja pose:

- les specs d'outils peuvent maintenant declarer un `ui_panel`
- `BoardController` utilise ce metadata pour afficher les panneaux BCS / Vibrance / Crop
- le mode crop handle ne depend plus directement d'un test en dur sur l'id `crop`
- `BoardPage` expose maintenant des panneaux nommes (`bcs`, `vibrance`, `crop`) au lieu d'une simple serie de toggles specialises
- `BoardController` lit/ecrit deja une partie des valeurs d'edition via des etats de panel, pas directement widget par widget
- les mises a jour de la stack passent desormais par une voie generique pilotee par les specs des tools
- les specs d'outils declarent aussi leurs `ui_settings_keys`, ce qui permet au controller de relire un panel avec moins de connaissance metier codee en dur
- le pont `tool spec <-> panel state` commence maintenant a vivre dans `core/board_edit/panels.py`
- la synchro UI et le reset des outils passent maintenant par les specs des tools, plutot que par des etats de panel hardcodes un par un dans `BoardController`
- les specs d'outils commencent aussi a decrire leurs controles UI (`ui_controls`), et `BoardPage` relit/ecrit maintenant une partie des panels a partir de cette metadata
- une partie des callbacks de panel image passe maintenant par une voie plus generique cote controller, au lieu de multiplier les handlers presque identiques par tool

Ce qui reste volontairement a part:

- l'interaction scene du crop (handles, drag dans la vue) reste un sujet d'interaction de scene, pas un simple panel de reglages

### Etape 3. Sortir les items de scene de `board_controller.py`

Objectif:

- faire tomber drastiquement la taille du fichier

Travail:

- deplacer `BoardImageItem`, `BoardVideoItem`, `BoardSequenceItem`, `BoardNoteItem`, `BoardGroupItem`
- garder uniquement leur orchestration dans le controller

Statut: en cours le 2026-04-18

Premier pas deja pose:

- les items de scene ont ete extraits vers `core/board_scene/items.py`
- `BoardController` importe maintenant ces classes au lieu de les definir inline
- le fichier a nettement maigri sans changer le comportement visible
- les workers/media helpers ont ete extraits vers `core/board_edit/workers.py`
- les petits composants UI du board ont ete extraits vers `core/board_scene/dialogs.py`
- les operations de groupes et une partie du mapping `scene <-> groups_tree` commencent a sortir vers `core/board_scene/groups.py`
- la selection ciblee depuis le `groups_tree` et une partie des regles de renommage du tree passent maintenant aussi par `core/board_scene/groups.py`
- les regles d'actions disponibles dans le context menu du `groups_tree` commencent aussi a etre centralisees dans `core/board_scene/groups.py`
- les regles de click/double-click et de nom editable du `groups_tree` commencent aussi a s'appuyer sur `core/board_scene/groups.py`
- les helpers purs de `board_state` et de migration de payload commencent a sortir vers `core/board_state/payload.py`
- l'etat temporaire et les helpers du flux `apply payload` commencent a sortir vers `core/board_state/apply.py`
- la reconstruction concrete des items et groupes depuis le payload commence a sortir vers `core/board_state/rebuild.py`

### Sous-chantier termine: groups tree / groupes de scene

Statut: termine le 2026-04-18

Ce qui est maintenant sorti:

- les operations de groupes et une partie du mapping `scene <-> groups_tree` vivent dans `core/board_scene/groups.py`
- la selection ciblee depuis le `groups_tree` passe par `core/board_scene/groups.py`
- une partie des regles de renommage du tree passe par `core/board_scene/groups.py`
- les regles d'actions disponibles dans le context menu du `groups_tree` commencent a etre centralisees dans `core/board_scene/groups.py`
- les regles de click/double-click et de nom editable du `groups_tree` s'appuient aussi sur `core/board_scene/groups.py`
- la logique de filtrage groupable, ungroup, et regroupement "par bloc" pour certaines operations de layout vit maintenant aussi dans `core/board_scene/groups.py`

### Sous-chantier termine: board state / apply payload

Statut: termine le 2026-04-18

Ce qui est maintenant sorti:

- clonage/normalisation du payload
- comptage et synchronisation des overrides du payload
- migration des anciens overrides vers le format courant
- etat temporaire du flux `apply payload`
- partition des entries du payload
- reconstruction des items et groupes depuis le payload

Le flux est encore orchestre par `BoardController`, mais les briques critiques ne vivent plus toutes dedans.

### Etape 4. Isoler les workflows media annexes

Objectif:

- decouper les conversions et previews longues du controller principal

Travail:

- sortir les workers image/video/exr si possible vers un module dedie


## Sous-chantier termine: board overrides

Statut: termine le 2026-04-18

Ce qui est maintenant sorti:

- les regles de merge/update/remove des overrides commencent a sortir vers `core/board_state/overrides.py`
- `BoardController` ne construit deja plus seul certaines variantes d'override image/video/preview
- l'application des overrides aux items et le reapply de scene commencent aussi a sortir vers `core/board_state/overrides.py`
- la conversion des payloads de preview en pixmap et certaines mises a jour d'override post-preview sortent aussi vers `core/board_state/overrides.py`
- les commits d'override image/video depuis le focus mode passent maintenant aussi par `core/board_state/overrides.py`
- le traitement post-preview du focus image/EXR vit maintenant en grande partie dans `core/board_state/overrides.py`
- l'ancien chemin `_apply_payload` reapplique lui aussi les overrides via les memes helpers dedies
- le renommage de medias deplace maintenant les overrides image et video via un helper commun


## Tests cibles ajoutes

Statut: en cours le 2026-04-18

Une premiere base de tests `unittest` existe maintenant dans `tests/` pour proteger les modules purs extraits:

- `tests/test_board_tool_stack.py`
- `tests/test_board_state_payload.py`
- `tests/test_board_state_overrides.py`
- `tests/test_board_scene_groups.py`

Couverture visee dans cette premiere passe:

- normalisation et efficacite de `tool_stack`
- parsing/synchronisation du `board_state`
- merge/commit/rename d'overrides
- logique groupes / `groups_tree` pure

Commande de verification actuelle:

- `venv\Scripts\python.exe -m unittest discover -s tests -v`

## Nouveau chantier: rationalisation des tools

Statut: en cours le 2026-04-18

Constat:

- l'ancienne separation par dossier technique global a aide a sortir du monolithe
- mais elle etait peu agreable pour l'auteur d'un tool complet
- `crop` montrait aussi qu'un tool interactif a besoin de vivre avec sa logique de scene, pas a cote dans un namespace trop generique

Direction retenue:

- converger vers `tools/board_tools/<tool_id>/`
- y regrouper les capacites par tool:
  - `tool.py`
  - `image.py`
  - `scene.py`
- ne plus ajouter de couche de compatibilite interne; le code actif passe par `tools/board_tools/<tool_id>/`

Premier pas deja pose:

- `bcs`, `vibrance` et `crop` vivent maintenant aussi dans `tools/board_tools/*`
- les registries edit/image savent maintenant decouvrir ces nouveaux dossiers
- les anciens points d'entree de compatibilite internes ont ete supprimes; le runtime scene du crop vit uniquement dans `tools/board_tools/crop/scene.py`
- une registry unifiee `tools/board_tools/registry.py` expose maintenant explicitement les capacites `tool/image/scene` de chaque tool
- `BoardController` branche maintenant l'interaction de scene via ces capacites, au lieu de dependre d'un test nominal sur `crop`
- le runtime de scene d'un tool n'est plus seulement un module implicite: `crop` expose maintenant un `SCENE_RUNTIME` formel via `BoardToolSceneRuntime`
- les anciens wrappers techniques globaux ont ete supprimes
- la vraie logique edit/image residuelle a ete remontee dans `tools/board_tools/edit.py` et `tools/board_tools/image.py`
- apres audit des imports internes, la couche historique a pu etre retiree completement
- les tools peuvent declarer `default_for` pour construire les stacks par defaut sans hardcode central
- les tools de scene peuvent maintenant exposer `reset_focus_item`, ce qui evite au focus controller de connaitre les details internes d'un tool comme le crop
- les nouveaux overrides sauvegardes ne recopient plus les anciens champs scalaires `brightness` / `crop_left`; la `tool_stack` est maintenant la source de verite
