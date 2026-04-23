# Board Scalability Todo

Date: 2026-04-22

Cette todo suit la transition du board vers une architecture vraiment scalable. Elle complete `board_scalability_target.md` avec des taches executables.

## Phase 1. Contrats De Tools

- [x] Ajouter une validation explicite des specs de tools.
- [x] Verifier unicite et normalisation des ids.
- [x] Verifier que `supports` et `default_for` utilisent des media kinds connus.
- [x] Verifier que les `ui_controls` sont coherents avec les settings declares.
- [x] Verifier que les tools avec `scene.py` exposent un `SCENE_RUNTIME` valide.
- [x] Ajouter des tests de contrat pour les tools actuels.
- [x] Rendre les erreurs de tool lisibles et non bloquantes dans l'UI ou les logs de demarrage.

## Phase 2. Pipeline De Mutations

- [x] Ajouter un objet `BoardAction`.
- [x] Ajouter un premier service de commit de mutation board.
- [x] Faire passer les mutations simples par ce service: move, delete, group, rename.
- [x] Brancher history, dirty state, group refresh et save via le pipeline commun.
- [x] Grouper les interactions longues en une seule mutation historique.

## Phase 3. Preview Runtime

- [x] Ajouter un objet `PreviewRequest`.
- [x] Donner un id/hash aux previews.
- [x] Ignorer les resultats de previews obsoletes.
- [x] Centraliser debounce/cancel/replace.
- [x] Ajouter un busy/pending state fiable.

## Phase 4. Board State Et Migrations

- [x] Ajouter une version de schema au payload board.
- [x] Creer `core/board_state/migrations.py`.
- [x] Tester les migrations d'anciens payloads vers le format courant.
- [x] Documenter le contrat save/load.
- [x] Verifier que les nouveaux saves restent centres sur `tool_stack`.

## Phase 5. UI Edit Panel

- [ ] Extraire la construction du panneau edit de `BoardPage`.
- [ ] Creer un widget ou builder pour les panels de tools.
- [ ] Generer davantage de controls depuis `ToolUiControlSpec`.
- [ ] Eviter toute nouvelle logique tool-specific dans `BoardPage`.

## Phase 6. Commandes Et Raccourcis Globaux

- [x] Documenter la cible globale commandes/raccourcis.
- [x] Creer `core/commands` sans dependance Qt.
- [x] Ajouter `AppCommand`, `CommandContext` et `CommandResult`.
- [x] Ajouter `CommandRegistry` avec validation des ids/scopes.
- [x] Ajouter `ShortcutBinding` et resolution defaults + overrides.
- [x] Ajouter detection de conflits de raccourcis par scope.
- [x] Ajouter tests purs de registry, bindings et conflits.
- [x] Declarer les premieres commandes globales/board.
- [x] Brancher un dispatcher global puis un dispatcher board.
- [x] Brancher les raccourcis Qt au niveau fenetre.
- [x] Lire les overrides depuis les settings.
- [x] Ajouter une premiere UI Settings pour editer les overrides.

## Definition De Done

Une phase est consideree terminee quand:

- elle a une implementation bornee
- elle a des tests ou une validation claire
- elle ne reintroduit pas d'acces prives aux zones extensibles
- elle est documentee dans les docs board si elle change le modele mental
