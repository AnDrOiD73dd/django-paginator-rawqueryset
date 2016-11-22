from django.core.paginator import Page, Paginator as DefaultPaginator
from django.db.models.query import RawQuerySet
from django.db import connections

class DatabaseNotSupportedException(Exception):
    pass

class RawQuerySetPaginator(DefaultPaginator):
    "An efficient paginator for RawQuerySets."
    def __init__(self,object_list,per_page,orphans=0,allow_empty_first_page=True):
        super(RawQuerySetPaginator,self).__init__(object_list,per_page,orphans,allow_empty_first_page)
        self.raw_query_set = self.object_list
        self.connection = connections[self.raw_query_set.db]
        self._count = None

    def _get_count(self):
        if self._count is None:
            cursor = self.connection.cursor()
            count_query = 'SELECT COUNT(*) FROM (%s) AS sub_query_for_count' % self.raw_query_set.raw_query
            cursor.execute(count_query,self.raw_query_set.params)
            self._count = cursor.fetchone()[0]
        return self._count
    count = property(_get_count)

    ## mysql, postgresql, and sqlite can all use this syntax
    def __get_limit_offset_query(self,limit,offset):
        return '''SELECT * FROM (%s) as sub_query_for_pagination 
                LIMIT %s OFFSET %s''' % (self.raw_query_set.raw_query, limit, offset)
    mysql_getquery = __get_limit_offset_query
    postgresql_getquery = __get_limit_offset_query
    sqlite_getquery = __get_limit_offset_query

    ## Get the oracle query, but check the version first
    ## Query is only supported in oracle version >= 12.1
    ## I have no access to oracle and have no idea if this code works
    ## TODO:TESTING
    def oracle_getquery(self,limit,offset):
        (major_version,minor_version) = self.connection.oracle_version[0:2]
        if major_version < 12 or (major_version == 12 and minor_version < 1):
            raise DatabaseNotSupportedException('Oracle version must be 12.1 or higher')
        return '''SELECT * FROM (%s) as sub_query_for_pagination 
                  OFFSET %s ROWS FETCH NEXT %s ROWS ONLY''' % (self.raw_query_set.raw_query, offset, limit)

    def firebird_getquery(self,limit,offset):## TODO:TESTING
        return '''SELECT FIRST %s SKIP %s * 
                FROM (%s) as sub_query_for_pagination'''  % (limit,offset,self.raw_query_set.raw_query)

    def page(self,number):
        number = self.validate_number(number)
        offset = (number -1 ) * self.per_page
        limit = self.per_page
        if offset + limit + self.orphans >= self.count:
            limit = self.count - offset
        database_vendor = self.connection.vendor
        try:
            query_with_limit = getattr(self,'%s_getquery' % database_vendor)(limit,offset)
        except AttributeError:
            raise DatabaseNotSupportedException('%s is not supported by RawQuerySetPaginator' % database_vendor)
        return Page(list(self.raw_query_set.model.objects.raw(query_with_limit,self.raw_query_set.params)), number, self)

def Paginator(object_list,per_page,orphans=0,allow_empty_first_page=True):
    if isinstance(object_list,RawQuerySet):
        return RawQuerySetPaginator(object_list,per_page,orphans,allow_empty_first_page)
    else:
        return DefaultPaginator(object_list,per_page,orphans,allow_empty_first_page)
