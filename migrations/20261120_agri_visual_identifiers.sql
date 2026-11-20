/*
  FermeSync agricultural setup visual identifiers
  Run manually after reviewing and backing up the database.
*/

IF COL_LENGTH('agr.Farm', 'FarmColour') IS NULL
    ALTER TABLE agr.Farm ADD FarmColour nvarchar(7) NOT NULL CONSTRAINT DF_agr_Farm_FarmColour DEFAULT '#2f7d32';

IF COL_LENGTH('agr.Crop', 'CropIcon') IS NULL
    ALTER TABLE agr.Crop ADD CropIcon nvarchar(50) NOT NULL CONSTRAINT DF_agr_Crop_CropIcon DEFAULT 'fa-seedling';

IF COL_LENGTH('agr.Crop', 'CropThemeColor') IS NULL
    ALTER TABLE agr.Crop ADD CropThemeColor nvarchar(20) NULL;

UPDATE agr.Farm
SET FarmColour = '#2f7d32'
WHERE FarmColour IS NULL OR FarmColour = '';

UPDATE agr.Crop
SET CropIcon =
    CASE
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%potato%' THEN 'fa-potato'
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%onion%' THEN 'fa-onion'
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%maize%' OR LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%corn%' THEN 'fa-wheat-awn'
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%citrus%' THEN 'fa-lemon'
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%butternut%' THEN 'fa-carrot'
        WHEN LOWER(COALESCE(CropCode, '') + ' ' + COALESCE(CropDescription, '')) LIKE '%bean%' THEN 'fa-leaf'
        ELSE 'fa-seedling'
    END
WHERE CropIcon IS NULL OR CropIcon = '' OR CropIcon = 'fa-seedling';
