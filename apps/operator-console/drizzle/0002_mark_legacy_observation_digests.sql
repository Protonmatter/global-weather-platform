UPDATE `observations`
SET `content_digest` = 'legacy:unknown'
WHERE `content_digest` = '';
