# encoding: utf-8

import copy
from nose.tools import eq_
from collections import defaultdict

import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
from ckan.migration.migrate_package_activity import (migrate_dataset,
                                                     wipe_activity_detail)
from ckan.model.activity import package_activity_list
from ckan import model


class TestMigrateDataset(object):
    def setup(self):
        helpers.reset_db()

    @classmethod
    def teardown_class(cls):
        helpers.reset_db()

    def test_migration(self):
        # Test that the migration correctly takes the package_revision (etc)
        # tables and populates the Activity.data, i.e. it does it the same as
        # if you made a change to the dataset with the current version of CKAN
        # and the Activity was created by activity_stream_item().
        dataset = factories.Dataset(resources=[
            {u'url': u'http://example.com/a.csv', u'format': u'csv'}
        ])
        activity = package_activity_list(dataset['id'], 0, 0)[0]
        activity_data_as_it_should_be = copy.deepcopy(activity.data)

        # Remove 'activity.data.package' to provoke the migration to regenerate
        # it from package_revision (etc)
        activity = model.Activity.get(activity.id)
        del activity.data['package']
        model.repo.commit_and_remove()
        migrate_dataset(dataset['name'], {})

        activity_data_migrated = \
            package_activity_list(dataset['id'], 0, 0)[0].data
        eq_(activity_data_as_it_should_be, activity_data_migrated)

    def test_migration_with_multiple_revisions(self):
        dataset = factories.Dataset(resources=[
            {u'url': u'http://example.com/a.csv', u'format': u'csv'}
        ])
        dataset['title'] = u'Title 2'
        helpers.call_action(u'package_update', **dataset)
        dataset['title'] = u'Title 3'
        helpers.call_action(u'package_update', **dataset)

        activity = package_activity_list(dataset['id'], 0, 0)[1]
        activity_data_as_it_should_be = copy.deepcopy(activity.data)

        # Remove 'activity.data.package' to provoke the migration to regenerate
        # it from package_revision (etc)
        activity = model.Activity.get(activity.id)
        del activity.data['package']
        model.repo.commit_and_remove()
        migrate_dataset(dataset['name'], {})

        activity_data_migrated = \
            package_activity_list(dataset['id'], 0, 0)[1].data
        eq_(activity_data_as_it_should_be, activity_data_migrated)
        eq_(activity_data_migrated['package']['title'], u'Title 2')

    def test_a_contemporary_activity_needs_no_migration(self):
        # An Activity created by a change under the current CKAN should not
        # need a migration - check it does a nop
        dataset = factories.Dataset(resources=[
            {u'url': u'http://example.com/a.csv', u'format': u'csv'}
        ])
        activity = package_activity_list(dataset['id'], 0, 0)[0]
        activity_data_before = copy.deepcopy(activity.data)

        migrate_dataset(dataset['name'], {})

        activity_data_after = package_activity_list(dataset['id'], 0, 0)[0].data
        eq_(activity_data_before, activity_data_after)

    def test_revision_missing(self):
        dataset = factories.Dataset(resources=[
            {u'url': u'http://example.com/a.csv', u'format': u'csv'}
        ])
        # delete a part of the revision, so package_show for the revision will
        # return NotFound
        model.Session.query(model.PackageRevision).delete()
        model.Session.commit()
        # delete 'activity.data.package.resources' so it needs migrating
        activity = package_activity_list(dataset['id'], 0, 0)[0]
        activity = model.Activity.get(activity.id)
        del activity.data['package']['resources']
        model.Session.commit()

        errors = defaultdict(int)
        migrate_dataset(dataset['name'], errors)

        eq_(dict(errors), {u'Revision missing': 1})
        activity_data_migrated = \
            package_activity_list(dataset['id'], 0, 0)[0].data
        # the title is there so the activity stream can display it
        eq_(activity_data_migrated['package']['title'], u'Test Dataset')
        # the rest of the dataset is missing - better that than just the
        # dictized package without resources, extras etc
        assert u'resources' not in activity_data_migrated['package']

    def test_revision_and_data_missing(self):
        dataset = factories.Dataset(resources=[
            {u'url': u'http://example.com/a.csv', u'format': u'csv'}
        ])
        # delete a part of the revision, so package_show for the revision will
        # return NotFound
        model.Session.query(model.PackageRevision).delete()
        model.Session.commit()
        # delete 'activity.data.package' so it needs migrating AND the package
        # title won't be available, so we test how the migration deals with
        # that
        activity = package_activity_list(dataset['id'], 0, 0)[0]
        activity = model.Activity.get(activity.id)
        del activity.data['package']
        model.Session.commit()

        errors = defaultdict(int)
        migrate_dataset(dataset['name'], errors)

        eq_(dict(errors), {u'Revision missing': 1})
        activity_data_migrated = \
            package_activity_list(dataset['id'], 0, 0)[0].data
        # the title is there so the activity stream can display it
        eq_(activity_data_migrated['package']['title'], u'unknown')
        assert u'resources' not in activity_data_migrated['package']


class TestWipeActivityDetail(object):
    def test_wipe_activity_detail(self):
        dataset = factories.Dataset()
        user = factories.User()
        activity = factories.Activity(
            user_id=user['id'], object_id=dataset['id'], revision_id=None,
            activity_type=u'new package',
            data={
                u'package': copy.deepcopy(dataset),
                u'actor': u'Mr Someone',
            })
        ad = model.ActivityDetail(
            activity_id=activity['id'], object_id=dataset['id'],
            object_type=u'package', activity_type=u'new package')
        model.Session.add(ad)
        model.Session.commit()
        eq_(model.Session.query(model.ActivityDetail).count(), 1)
        wipe_activity_detail(delete_activity_detail=u'y')
        eq_(model.Session.query(model.ActivityDetail).count(), 0)

    def test_dont_wipe_activity_detail(self):
        dataset = factories.Dataset()
        user = factories.User()
        activity = factories.Activity(
            user_id=user['id'], object_id=dataset['id'], revision_id=None,
            activity_type=u'new package',
            data={
                u'package': copy.deepcopy(dataset),
                u'actor': u'Mr Someone',
            })
        ad = model.ActivityDetail(
            activity_id=activity['id'], object_id=dataset['id'],
            object_type=u'package', activity_type=u'new package')
        model.Session.add(ad)
        model.Session.commit()
        eq_(model.Session.query(model.ActivityDetail).count(), 1)
        wipe_activity_detail(delete_activity_detail=u'n')  # i.e. don't do it!
        eq_(model.Session.query(model.ActivityDetail).count(), 1)
