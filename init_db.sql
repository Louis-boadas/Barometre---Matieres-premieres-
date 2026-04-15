-- ============================================================
--  init_db.sql — Initialisation de la base "barometre"
--  À exécuter une seule fois sur le serveur SQL Server
-- ============================================================

USE barometre;
GO

-- ------------------------------------------------------------
-- Table de configuration : liste des indices à récupérer
-- ------------------------------------------------------------
IF NOT EXISTS (
    SELECT * FROM sys.tables WHERE name = 'parametres'
)
BEGIN
    CREATE TABLE parametres (
        id   INT IDENTITY(1,1) PRIMARY KEY,
        URL  VARCHAR(500)  NOT NULL,   -- URL de l'API Usine Nouvelle pour cet indice
        TBDD VARCHAR(100)  NOT NULL    -- Nom de la table SQL de destination
    );
    PRINT 'Table parametres créée.';
END
ELSE
    PRINT 'Table parametres déjà existante — ignorée.';
GO

-- ------------------------------------------------------------
-- Exemple de création d'une table d'indice
-- (répéter pour chaque indice référencé dans parametres.TBDD)
-- ------------------------------------------------------------
IF NOT EXISTS (
    SELECT * FROM sys.tables WHERE name = 'acier'
)
BEGIN
    CREATE TABLE acier (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        code_indice     VARCHAR(50)   NULL,
        name            VARCHAR(255)  NULL,
        date            DATETIME      NOT NULL UNIQUE,
        valeur          FLOAT         NULL,
        unite_de_mesure VARCHAR(100)  NULL,
        flag            VARCHAR(20)   NULL   -- 'Réelle' ou 'Ajouté'
    );
    PRINT 'Table acier créée.';
END
GO

-- ------------------------------------------------------------
-- Exemples d'insertion dans parametres
-- (adapter les URLs et noms de tables à votre configuration)
-- ------------------------------------------------------------
-- INSERT INTO parametres (URL, TBDD) VALUES
--     ('https://www.usinenouvelle.com/api/indices/ACIER_CODE', 'acier'),
--     ('https://www.usinenouvelle.com/api/indices/CUIVRE_CODE', 'cuivre'),
--     ('https://www.usinenouvelle.com/api/indices/PETROLE_CODE', 'petrole');
-- GO

PRINT '=== Initialisation terminée ===';
GO
