import unittest
from temp_dir import within_temp_dir
import csv
import textwrap
from StringIO import StringIO
import subprocess

from csvtools.test import ReaderWriter, csv_reader
from csvtools.lib import FieldsMap
import csvtools.extract_map as m


class TestMap(unittest.TestCase):

    def map_reader(self):
        return csv_reader('''\
            id,a,b
            1,aa,bb
            ''')

    def test_instantiate_with_non_matching_header_line_is_an_error(self):
        with self.assertRaises(m.MissingFieldError):
            reader = self.map_reader()
            m.Mapper('idx', ['a', 'b'], reader, appender=None)

        with self.assertRaises(m.MissingFieldError):
            reader = self.map_reader()
            m.Mapper('id', ['ax', 'b'], reader, appender=None)

        with self.assertRaises(m.ExtraFieldError):
            reader = self.map_reader()
            m.Mapper('id', ['b'], reader, appender=None)

        with self.assertRaises(m.InvalidReferenceFieldError):
            reader = self.map_reader()
            m.Mapper('id', ['id', 'a', 'b'], reader, appender=None)

    def test_new_creates_header(self):
        appender = ReaderWriter()
        m.Mapper.new('id', ['a', 'b'], appender=appender)

        self.assertEqual(1, len(appender.rows))
        self.assertListEqual(['id', 'a', 'b'], appender.rows[0])

    def test_new_map_can_be_used(self):
        appender = ReaderWriter()
        mapper = m.Mapper.new('id', ['a', 'b'], appender=appender)

        mapped_id = mapper.map(('aa', 'bb'))
        self.assertEqual(1, mapped_id)
        self.assertEqual(2, len(appender.rows))
        self.assertListEqual([1, 'aa', 'bb'], appender.rows[1])

    def test_map_new_value(self):
        reader = self.map_reader()
        appender = ReaderWriter()
        mapper = m.Mapper('id', ['a', 'b'], reader, appender)

        mapped_id = mapper.map(('aaa', 'bbb'))

        self.assertEqual(2, mapped_id)
        self.assertEqual(1, len(appender.rows))
        self.assertListEqual([2, 'aaa', 'bbb'], appender.rows[0])

    def test_map_existing_value(self):
        reader = self.map_reader()
        mapper = m.Mapper('id', ['a', 'b'], reader, appender=None)

        mapped_id = mapper.map(('aa', 'bb'))

        self.assertEqual(1, mapped_id)

    def test_unsorted_map_with_gaps_works_correctly(self):
        reader = csv_reader('''\
            id,a,b
            5,aaa,bbb
            1,aa,bb
            ''')
        appender = ReaderWriter()
        mapper = m.Mapper('id', ['a', 'b'], reader, appender)

        mapped_id = mapper.map(('a3', 'b3'))

        self.assertEqual(6, mapped_id)

    def test_map_with_different_field_order_read_in_properly(self):
        reader = csv_reader('''\
            b,id,a
            b,1,a
            ''')
        appender = ReaderWriter()
        mapper = m.Mapper('id', ['a', 'b'], reader, appender)

        mapped_id = mapper.map(('a', 'b'))

        self.assertEqual(1, mapped_id)

    def test_map_with_different_field_order_is_written_properly(self):
        reader = csv_reader('''\
            b,id,a
            b,1,a
            ''')
        appender = ReaderWriter()
        mapper = m.Mapper('id', ['a', 'b'], reader, appender)

        mapped_id = mapper.map(('aa', 'bb'))

        self.assertEqual(2, mapped_id)
        self.assertListEqual([['bb', 2, 'aa']], appender.rows)


class ExtractorFixture(object):

    def __init__(self):
        self.appender = ReaderWriter()
        self.mapper_reader = self._mapper_reader()
        self.mapper_appender = ReaderWriter()
        self.reader = self._reader()
        self.extractor = m.EntityExtractor(
            #                 in/output: ab_id    entity-mapper: id
            ref_field_map=FieldsMap.parse('id=ab_id'),
            #                 in/output: a, b     entity-mapper: a, other
            fields_map=FieldsMap.parse('a,other=b'),
            keep_fields=True)

    def _reader(self):
        return csv_reader('''\
            b,a,c
            b1,a1,c1
            b2,a2,c2
            b1,a1,c3
            ''')

    def _mapper_reader(self):
        return csv_reader('''\
            other,id,a
            b1,1,a1
            b3,3,a3
            ''')


class TestEntityExtractor(unittest.TestCase):

    def test_extract_new_mapper_entities(self):
        f = ExtractorFixture()
        f.extractor.use_new_mapper(f.mapper_appender)

        f.extractor.extract(f.reader, f.appender)

        self.assertListEqual(
            [
                ['id', 'a', 'other'],
                [1, 'a1', 'b1'],
                [2, 'a2', 'b2'],
            ],
            f.mapper_appender.rows)

    def test_extract_new_mapper_output(self):
        f = ExtractorFixture()
        f.extractor.use_new_mapper(f.mapper_appender)

        f.extractor.extract(f.reader, f.appender)

        self.assertListEqual(
            [
                ['b', 'a', 'c', 'ab_id'],
                ['b1', 'a1', 'c1', 1],
                ['b2', 'a2', 'c2', 2],
                ['b1', 'a1', 'c3', 1],
            ],
            f.appender.rows)

    def test_extract_existing_mapper_entities(self):
        f = ExtractorFixture()
        f.extractor.use_existing_mapper(f.mapper_reader, f.mapper_appender)

        f.extractor.extract(f.reader, f.appender)

        self.assertListEqual(
            [
                ['b2', 4, 'a2'],
            ],
            f.mapper_appender.rows)

    def test_extract_existing_mapper_output(self):
        f = ExtractorFixture()
        f.extractor.use_existing_mapper(f.mapper_reader, f.mapper_appender)

        f.extractor.extract(f.reader, f.appender)

        self.assertListEqual(
            [
                ['b', 'a', 'c', 'ab_id'],
                ['b1', 'a1', 'c1', 1],
                ['b2', 'a2', 'c2', 4],
                ['b1', 'a1', 'c3', 1],
            ],
            f.appender.rows)


class Test_script(unittest.TestCase):

    # integration tests

    STDIN = textwrap.dedent('''\
        b,a,c
        b1,a1,c1
        b2,a2,c2
        b1,a1,c3
        ''')

    ENTITIES = textwrap.dedent('''\
        other,id,a
        b1,1,a1
        b3,3,a3
        ''')

    ENTITIES_FILE = 'entities.csv'

    CMDLINE = ['csv_extract_map', 'a,other=b', 'id=ab_id', ENTITIES_FILE]

    def entities(self):
        with open(self.ENTITIES_FILE) as f:
            return list(csv.reader(f))

    def call_without_creating_entities_file(self):
        process = subprocess.Popen(
            self.CMDLINE,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(self.STDIN)

        self.assertEqual('', stderr, stderr)
        return list(csv.reader(StringIO(stdout)))

    def call_with_entities_file(self):
        with open(self.ENTITIES_FILE, 'w') as f:
            f.write(self.ENTITIES)
        return self.call_without_creating_entities_file()

    @within_temp_dir
    def test_extract_new_mapper_entities(self):
        self.call_without_creating_entities_file()

        self.assertListEqual(
            [
                ['id', 'a', 'other'],
                ['1', 'a1', 'b1'],
                ['2', 'a2', 'b2'],
            ],
            self.entities())

    @within_temp_dir
    def test_extract_new_mapper_output(self):
        stdout_rows = self.call_without_creating_entities_file()

        self.assertListEqual(
            [
                ['b', 'a', 'c', 'ab_id'],
                ['b1', 'a1', 'c1', '1'],
                ['b2', 'a2', 'c2', '2'],
                ['b1', 'a1', 'c3', '1'],
            ],
            stdout_rows)

    @within_temp_dir
    def test_extract_existing_mapper_entities(self):
        self.call_with_entities_file()

        self.assertListEqual(
            [
                ['other', 'id', 'a'],
                ['b1', '1', 'a1'],
                ['b3', '3', 'a3'],
                ['b2', '4', 'a2'],
            ],
            self.entities())

    @within_temp_dir
    def test_extract_existing_mapper_output(self):
        stdout_rows = self.call_with_entities_file()

        self.assertListEqual(
            [
                ['b', 'a', 'c', 'ab_id'],
                ['b1', 'a1', 'c1', '1'],
                ['b2', 'a2', 'c2', '4'],
                ['b1', 'a1', 'c3', '1'],
            ],
            stdout_rows)
