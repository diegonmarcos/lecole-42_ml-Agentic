"""
Advanced Metadata Filtering for Qdrant - TASK-037 & TASK-038

Provides rich metadata filtering capabilities:
- Temporal filters (date ranges, relative dates)
- Categorical filters (tags, categories, authors)
- Hierarchical filters (nested attributes)
- Numeric range filters
- Full-text search on metadata
- Combined filters with AND/OR logic
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Optional, Union

from qdrant_client import models

logger = logging.getLogger(__name__)


class FilterOperator(Enum):
    """Filter comparison operators"""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    BETWEEN = "between"


class LogicalOperator(Enum):
    """Logical operators for combining filters"""

    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class MetadataFilter:
    """
    Single metadata filter condition.

    Examples:
        # Date filter
        MetadataFilter(field="created_at", operator=FilterOperator.GREATER_THAN, value="2024-01-01")

        # Category filter
        MetadataFilter(field="category", operator=FilterOperator.IN, value=["tech", "science"])

        # Numeric range
        MetadataFilter(field="score", operator=FilterOperator.BETWEEN, value=[0.7, 1.0])
    """

    field: str
    operator: FilterOperator
    value: Any

    def to_qdrant_condition(self) -> models.Condition:
        """Convert to Qdrant condition"""
        field_name = self.field

        if self.operator == FilterOperator.EQUALS:
            return models.FieldCondition(
                key=field_name, match=models.MatchValue(value=self.value)
            )

        if self.operator == FilterOperator.NOT_EQUALS:
            return models.Filter(
                must_not=[
                    models.FieldCondition(
                        key=field_name, match=models.MatchValue(value=self.value)
                    )
                ]
            )

        if self.operator == FilterOperator.IN:
            return models.FieldCondition(
                key=field_name, match=models.MatchAny(any=self.value)
            )

        if self.operator == FilterOperator.NOT_IN:
            return models.Filter(
                must_not=[
                    models.FieldCondition(
                        key=field_name, match=models.MatchAny(any=self.value)
                    )
                ]
            )

        if self.operator in [
            FilterOperator.GREATER_THAN,
            FilterOperator.GREATER_THAN_OR_EQUAL,
        ]:
            gte = self.operator == FilterOperator.GREATER_THAN_OR_EQUAL
            return models.FieldCondition(
                key=field_name,
                range=models.Range(
                    gte=self.value if gte else None, gt=self.value if not gte else None
                ),
            )

        if self.operator in [
            FilterOperator.LESS_THAN,
            FilterOperator.LESS_THAN_OR_EQUAL,
        ]:
            lte = self.operator == FilterOperator.LESS_THAN_OR_EQUAL
            return models.FieldCondition(
                key=field_name,
                range=models.Range(
                    lte=self.value if lte else None, lt=self.value if not lte else None
                ),
            )

        if self.operator == FilterOperator.BETWEEN:
            min_val, max_val = self.value
            return models.FieldCondition(
                key=field_name, range=models.Range(gte=min_val, lte=max_val)
            )

        if self.operator == FilterOperator.CONTAINS:
            # Full-text search on field
            return models.FieldCondition(
                key=field_name, match=models.MatchText(text=self.value)
            )

        raise ValueError(f"Unsupported operator: {self.operator}")


@dataclass
class CompositeFilter:
    """
    Composite filter with logical operators.

    Examples:
        # AND condition
        CompositeFilter(
            operator=LogicalOperator.AND,
            filters=[
                MetadataFilter("category", FilterOperator.EQUALS, "tech"),
                MetadataFilter("score", FilterOperator.GREATER_THAN, 0.8)
            ]
        )

        # OR condition
        CompositeFilter(
            operator=LogicalOperator.OR,
            filters=[...]
        )

        # Nested (category=tech AND (score>0.8 OR priority=high))
        CompositeFilter(
            operator=LogicalOperator.AND,
            filters=[
                MetadataFilter("category", FilterOperator.EQUALS, "tech"),
                CompositeFilter(
                    operator=LogicalOperator.OR,
                    filters=[
                        MetadataFilter("score", FilterOperator.GREATER_THAN, 0.8),
                        MetadataFilter("priority", FilterOperator.EQUALS, "high")
                    ]
                )
            ]
        )
    """

    operator: LogicalOperator
    filters: List[Union[MetadataFilter, "CompositeFilter"]]

    def to_qdrant_filter(self) -> models.Filter:
        """Convert to Qdrant filter"""
        conditions = []

        for f in self.filters:
            if isinstance(f, MetadataFilter):
                condition = f.to_qdrant_condition()
            else:  # CompositeFilter
                condition = f.to_qdrant_filter()

            conditions.append(condition)

        if self.operator == LogicalOperator.AND:
            return models.Filter(must=conditions)
        if self.operator == LogicalOperator.OR:
            # OR in Qdrant is represented with should
            return models.Filter(should=conditions)
        if self.operator == LogicalOperator.NOT:
            return models.Filter(must_not=conditions)

        raise ValueError(f"Unsupported operator: {self.operator}")


class TemporalFilter:
    """
    Helper for common temporal filters.

    Examples:
        # Last 7 days
        TemporalFilter.last_n_days("created_at", 7)

        # This month
        TemporalFilter.current_month("created_at")

        # Date range
        TemporalFilter.date_range("created_at", "2024-01-01", "2024-12-31")
    """

    @staticmethod
    def last_n_days(field: str, days: int) -> MetadataFilter:
        """Documents from last N days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return MetadataFilter(
            field=field,
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=cutoff.isoformat(),
        )

    @staticmethod
    def last_n_hours(field: str, hours: int) -> MetadataFilter:
        """Documents from last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return MetadataFilter(
            field=field,
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=cutoff.isoformat(),
        )

    @staticmethod
    def current_month(field: str) -> MetadataFilter:
        """Documents from current month"""
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        return MetadataFilter(
            field=field,
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=start_of_month.isoformat(),
        )

    @staticmethod
    def current_year(field: str) -> MetadataFilter:
        """Documents from current year"""
        now = datetime.utcnow()
        start_of_year = datetime(now.year, 1, 1)
        return MetadataFilter(
            field=field,
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=start_of_year.isoformat(),
        )

    @staticmethod
    def date_range(field: str, start_date: str, end_date: str) -> MetadataFilter:
        """Documents in date range"""
        return MetadataFilter(
            field=field, operator=FilterOperator.BETWEEN, value=[start_date, end_date]
        )

    @staticmethod
    def before_date(field: str, date: str) -> MetadataFilter:
        """Documents before date"""
        return MetadataFilter(
            field=field, operator=FilterOperator.LESS_THAN, value=date
        )

    @staticmethod
    def after_date(field: str, date: str) -> MetadataFilter:
        """Documents after date"""
        return MetadataFilter(
            field=field, operator=FilterOperator.GREATER_THAN, value=date
        )


class CategoryFilter:
    """
    Helper for categorical filters.

    Examples:
        # Single category
        CategoryFilter.by_category("tech")

        # Multiple categories
        CategoryFilter.by_categories(["tech", "science"])

        # By author
        CategoryFilter.by_author("john_doe")

        # By tags
        CategoryFilter.has_tags(["python", "machine-learning"])
    """

    @staticmethod
    def by_category(category: str, field: str = "category") -> MetadataFilter:
        """Filter by single category"""
        return MetadataFilter(
            field=field, operator=FilterOperator.EQUALS, value=category
        )

    @staticmethod
    def by_categories(categories: List[str], field: str = "category") -> MetadataFilter:
        """Filter by multiple categories (OR)"""
        return MetadataFilter(field=field, operator=FilterOperator.IN, value=categories)

    @staticmethod
    def by_author(author: str, field: str = "author") -> MetadataFilter:
        """Filter by author"""
        return MetadataFilter(field=field, operator=FilterOperator.EQUALS, value=author)

    @staticmethod
    def has_tags(tags: List[str], field: str = "tags") -> CompositeFilter:
        """Filter by tags (must have all tags)"""
        filters: List[Union[MetadataFilter, CompositeFilter]] = [
            MetadataFilter(field=field, operator=FilterOperator.CONTAINS, value=tag)
            for tag in tags
        ]
        return CompositeFilter(operator=LogicalOperator.AND, filters=filters)

    @staticmethod
    def has_any_tag(tags: List[str], field: str = "tags") -> MetadataFilter:
        """Filter by tags (has at least one tag)"""
        return MetadataFilter(field=field, operator=FilterOperator.IN, value=tags)

    @staticmethod
    def by_source(source: str, field: str = "source") -> MetadataFilter:
        """Filter by source"""
        return MetadataFilter(field=field, operator=FilterOperator.EQUALS, value=source)


class NumericFilter:
    """
    Helper for numeric filters.

    Examples:
        # Score above threshold
        NumericFilter.above_threshold("score", 0.8)

        # Score in range
        NumericFilter.in_range("score", 0.7, 1.0)

        # Top percentile
        NumericFilter.above_threshold("rank", 95)
    """

    @staticmethod
    def above_threshold(field: str, threshold: float) -> MetadataFilter:
        """Values above threshold"""
        return MetadataFilter(
            field=field, operator=FilterOperator.GREATER_THAN_OR_EQUAL, value=threshold
        )

    @staticmethod
    def below_threshold(field: str, threshold: float) -> MetadataFilter:
        """Values below threshold"""
        return MetadataFilter(
            field=field, operator=FilterOperator.LESS_THAN_OR_EQUAL, value=threshold
        )

    @staticmethod
    def in_range(field: str, min_val: float, max_val: float) -> MetadataFilter:
        """Values in range"""
        return MetadataFilter(
            field=field, operator=FilterOperator.BETWEEN, value=[min_val, max_val]
        )

    @staticmethod
    def equals(field: str, value: float) -> MetadataFilter:
        """Exact value"""
        return MetadataFilter(field=field, operator=FilterOperator.EQUALS, value=value)


class HierarchicalFilter:
    """
    Helper for hierarchical/nested filters.

    Examples:
        # Nested path: user.department.name = "Engineering"
        HierarchicalFilter.by_path("user.department.name", "Engineering")

        # Nested category: docs.category.subcategory = "ML"
        HierarchicalFilter.by_path("docs.category.subcategory", "ML")
    """

    @staticmethod
    def by_path(path: str, value: Any) -> MetadataFilter:
        """Filter by nested path"""
        return MetadataFilter(field=path, operator=FilterOperator.EQUALS, value=value)

    @staticmethod
    def path_contains(path: str, value: Any) -> MetadataFilter:
        """Nested path contains value"""
        return MetadataFilter(field=path, operator=FilterOperator.CONTAINS, value=value)


class FilterBuilder:
    """
    Fluent interface for building complex filters.

    Usage:
        filter = (FilterBuilder()
            .add_category("tech")
            .add_date_range("created_at", "2024-01-01", "2024-12-31")
            .add_score_above("relevance", 0.8)
            .build()
        )
    """

    def __init__(self):
        self.filters: List[Union[MetadataFilter, CompositeFilter]] = []

    def add_filter(
        self, new_filter: Union[MetadataFilter, CompositeFilter]
    ) -> "FilterBuilder":
        """Add custom filter"""
        self.filters.append(new_filter)
        return self

    def add_category(self, category: str, field: str = "category") -> "FilterBuilder":
        """Add category filter"""
        self.filters.append(CategoryFilter.by_category(category, field))
        return self

    def add_categories(
        self, categories: List[str], field: str = "category"
    ) -> "FilterBuilder":
        """Add multiple category filter"""
        self.filters.append(CategoryFilter.by_categories(categories, field))
        return self

    def add_author(self, author: str, field: str = "author") -> "FilterBuilder":
        """Add author filter"""
        self.filters.append(CategoryFilter.by_author(author, field))
        return self

    def add_tags(
        self, tags: List[str], match_all: bool = True, field: str = "tags"
    ) -> "FilterBuilder":
        """Add tags filter"""
        if match_all:
            self.filters.append(CategoryFilter.has_tags(tags, field))
        else:
            self.filters.append(CategoryFilter.has_any_tag(tags, field))
        return self

    def add_date_range(
        self, field: str, start_date: str, end_date: str
    ) -> "FilterBuilder":
        """Add date range filter"""
        self.filters.append(TemporalFilter.date_range(field, start_date, end_date))
        return self

    def add_last_n_days(self, field: str, days: int) -> "FilterBuilder":
        """Add last N days filter"""
        self.filters.append(TemporalFilter.last_n_days(field, days))
        return self

    def add_score_above(self, field: str, threshold: float) -> "FilterBuilder":
        """Add score threshold filter"""
        self.filters.append(NumericFilter.above_threshold(field, threshold))
        return self

    def add_score_range(
        self, field: str, min_val: float, max_val: float
    ) -> "FilterBuilder":
        """Add score range filter"""
        self.filters.append(NumericFilter.in_range(field, min_val, max_val))
        return self

    def add_nested(self, path: str, value: Any) -> "FilterBuilder":
        """Add nested path filter"""
        self.filters.append(HierarchicalFilter.by_path(path, value))
        return self

    def build(
        self, operator: LogicalOperator = LogicalOperator.AND
    ) -> Optional[models.Filter]:
        """Build final Qdrant filter"""
        if not self.filters:
            return None

        if len(self.filters) == 1:
            f = self.filters[0]
            if isinstance(f, MetadataFilter):
                return models.Filter(must=[f.to_qdrant_condition()])
            return f.to_qdrant_filter()

        # Multiple filters
        composite = CompositeFilter(operator=operator, filters=self.filters)
        return composite.to_qdrant_filter()


# Example usage
def _demo() -> None:
    """Run a small demonstration of this module."""
    # Example 1: Simple category filter
    filter1 = CategoryFilter.by_category("tech")
    print("Simple filter:", filter1.to_qdrant_condition())

    # Example 2: Date range
    filter2 = TemporalFilter.last_n_days("created_at", 30)
    print("Date filter:", filter2.to_qdrant_condition())

    # Example 3: Composite filter with AND
    composite = CompositeFilter(
        operator=LogicalOperator.AND,
        filters=[
            CategoryFilter.by_category("tech"),
            TemporalFilter.last_n_days("created_at", 7),
            NumericFilter.above_threshold("score", 0.8),
        ],
    )
    print("Composite filter:", composite.to_qdrant_filter())

    # Example 4: Fluent builder
    filter4 = (
        FilterBuilder()
        .add_category("tech")
        .add_last_n_days("created_at", 7)
        .add_score_above("relevance", 0.8)
        .add_tags(["python", "ai"], match_all=True)
        .build()
    )
    print("Builder filter:", filter4)

    # Example 5: Nested OR condition
    # (category=tech OR category=science) AND score>0.8
    nested = CompositeFilter(
        operator=LogicalOperator.AND,
        filters=[
            CompositeFilter(
                operator=LogicalOperator.OR,
                filters=[
                    CategoryFilter.by_category("tech"),
                    CategoryFilter.by_category("science"),
                ],
            ),
            NumericFilter.above_threshold("score", 0.8),
        ],
    )
    print("Nested filter:", nested.to_qdrant_filter())


if __name__ == "__main__":
    _demo()
