"""Tests for slug generation utilities."""

from ia_utils.utils.slug import generate_slug


class TestGenerateSlug:
    def test_basic_slug(self):
        metadata = [
            ('creator', 'Spalteholz, Werner'),
            ('title', 'Hand atlas of human anatomy'),
            ('date', '1933'),
        ]
        slug = generate_slug(metadata, 'b31362138')
        assert slug == 'spalteholz-hand-atlas-human-anatomy-1933_b31362138'

    def test_removes_noise_words(self):
        metadata = [
            ('creator', 'Smith, John'),
            ('title', 'The anatomy of the human body'),
            ('date', '1900'),
        ]
        slug = generate_slug(metadata, 'test123')
        # "The", "of", "the" are noise words
        assert slug == 'smith-anatomy-human-body-1900_test123'

    def test_handles_missing_creator(self):
        metadata = [
            ('title', 'Medical dictionary'),
            ('date', '1950'),
        ]
        slug = generate_slug(metadata, 'test123')
        assert slug.startswith('unknown-')
        assert slug.endswith('_test123')

    def test_handles_missing_date(self):
        metadata = [
            ('creator', 'Jones'),
            ('title', 'Some book'),
        ]
        slug = generate_slug(metadata, 'test123')
        assert 'jones' in slug
        assert slug.endswith('_test123')

    def test_handles_edition(self):
        metadata = [
            ('creator', 'Author'),
            ('title', 'Book title'),
            ('date', '1920'),
            ('edition', '2nd Edition'),
        ]
        slug = generate_slug(metadata, 'test123')
        assert '2ndedition' in slug

    def test_handles_multiple_authors(self):
        metadata = [
            ('creator', 'Smith, John; Jones, Mary'),
            ('title', 'Collaborative work'),
            ('date', '1990'),
        ]
        slug = generate_slug(metadata, 'test123')
        # Should use first author only
        assert slug.startswith('smith-')

    def test_removes_special_characters_from_author(self):
        metadata = [
            ('creator', "O'Brien, Patrick"),
            ('title', 'Naval history'),
            ('date', '1980'),
        ]
        slug = generate_slug(metadata, 'test123')
        assert 'obrien' in slug

    def test_limits_title_to_four_words(self):
        metadata = [
            ('creator', 'Author'),
            ('title', 'One two three four five six seven'),
            ('date', '1900'),
        ]
        slug = generate_slug(metadata, 'test123')
        # Should only have first 4 significant words
        assert 'one-two-three-four' in slug
        assert 'five' not in slug

    def test_handles_empty_metadata(self):
        metadata = []
        slug = generate_slug(metadata, 'test123')
        assert slug.endswith('_test123')
        assert 'unknown' in slug
