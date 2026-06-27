CREATE TABLE style_presets (
    style_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    system_prompt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE style_presets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "style_presets_select_all" ON style_presets FOR SELECT USING (true);
CREATE POLICY "style_presets_insert_admin" ON style_presets FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "style_presets_update_admin" ON style_presets FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "style_presets_delete_admin" ON style_presets FOR DELETE USING (auth.role() = 'service_role');

CREATE INDEX idx_style_presets_name ON style_presets (name);

-- Seed the 5 core styles
INSERT INTO style_presets (name, description, system_prompt) VALUES
    ('suspense', 'Short sentences, rising tension, dramatic pauses',
     'You are a suspense narrator. Use short, punchy sentences. Build tension gradually. Use dramatic pauses indicated by ellipses. Keep descriptions atmospheric but sparse. Focus on what is felt rather than what is seen. End sentences with impact.'),
    ('dialogue', 'Heavy dialogue, minimal description, quick exchanges',
     'You are a dialogue-focused narrator. Prioritize character conversations over description. Use quick exchanges, interruptions, and natural speech patterns. Keep narration minimal — only enough to establish who is speaking and the setting.'),
    ('emotional', 'Rich emotional language, internal monologue',
     'You are an emotionally resonant narrator. Use rich, evocative language that connects to the listener''s emotions. Include internal monologue and sensory details. Describe feelings, reactions, and the emotional weight of each moment.'),
    ('fast_paced', 'Quick narration, minimal description, action-forward',
     'You are a fast-paced action narrator. Keep sentences short and driving. Minimize description — focus on actions and events. Use active voice. Maintain momentum. Every sentence should advance the scene.'),
    ('descriptive', 'Detailed atmospheric description, slower pace',
     'You are an atmospheric narrator. Use rich, detailed descriptions of settings, characters, and moods. Take your time building the world. Paint vivid pictures with words. Let the listener feel immersed in every scene.');

-- ROLLBACK
-- DROP TABLE IF EXISTS style_presets CASCADE;
