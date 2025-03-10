import pytest
import pandas as pd
import numpy as np
import os
import mlflow
import tempfile
import xgboost as xgb
from data_processing import prepare_data
from model_training import train_model
from model_evaluation import evaluate_model
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier


# Updated MLflow tracking fixture
@pytest.fixture(autouse=True)
def setup_mlflow_tracking(tmp_path):
    """Set up MLflow tracking for tests with a properly initialized experiment."""
    # Create a directory for MLflow tracking
    mlruns_dir = tmp_path / "mlruns"
    os.makedirs(mlruns_dir, exist_ok=True)

    # Set MLflow tracking URI to the temporary directory
    tracking_uri = f"file://{mlruns_dir}"
    mlflow.set_tracking_uri(tracking_uri)

    # Create a test experiment
    experiment_name = "test_experiment"
    try:
        # Check if experiment exists first
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            # Create new experiment
            experiment_id = mlflow.create_experiment(
                experiment_name,
                artifact_location=os.path.join(mlruns_dir, experiment_name),
            )
        else:
            experiment_id = experiment.experiment_id

        # Set as active experiment
        mlflow.set_experiment(experiment_name)
    except Exception as e:
        print(f"Warning: Failed to create MLflow experiment: {e}")

    # Make directories for artifacts that the tests might try to use
    artifacts_dir = tmp_path / "artifacts"
    data_dir = artifacts_dir / "data"
    models_dir = artifacts_dir / "models"
    evaluation_dir = artifacts_dir / "evaluation"
    training_dir = artifacts_dir / "training"
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(evaluation_dir, exist_ok=True)
    os.makedirs(training_dir, exist_ok=True)

    # Create a sample MLflow run to track artifacts under
    with mlflow.start_run(
        experiment_id=mlflow.get_experiment_by_name(experiment_name).experiment_id
    ) as run:
        mlflow.log_param("dummy", "value")

    yield

    # No cleanup needed for tmp_path as pytest handles it


class TestModelPipeline:
    @pytest.fixture
    def sample_data(self, tmp_path):
        """Fixture for sample churn data mimicking your CSV structure."""
        train_file = tmp_path / "churn-bigml-80.csv"
        test_file = tmp_path / "churn-bigml-20.csv"

        data = {
            "Total day minutes": [120.5, 150.3, 130.0, 140.0],
            "Customer service calls": [3, 2, 4, 1],
            "International plan": ["no", "yes", "no", "yes"],
            "Total intl minutes": [10.2, 8.5, 12.0, 9.5],
            "Total intl calls": [5, 4, 6, 3],
            "Total eve minutes": [200.0, 180.5, 190.0, 210.0],
            "Number vmail messages": [0, 5, 0, 3],
            "Voice mail plan": ["no", "yes", "no", "yes"],
            "Churn": [0, 1, 0, 1],  # Binary target
        }
        df = pd.DataFrame(data)
        train_df = df.iloc[:2]  # Training: 2 rows
        test_df = df.iloc[2:]  # Testing: 2 rows

        train_df.to_csv(train_file, index=False)
        test_df.to_csv(test_file, index=False)
        return str(train_file), str(test_file)

    @pytest.fixture
    def sample_train_data(self):
        """Fixture for preprocessed training data."""
        X_train = pd.DataFrame(
            {
                "Total day minutes": [120.5, 150.3],
                "Customer service calls": [3, 2],
                "International plan": ["no", "yes"],
                "Total intl minutes": [10.2, 8.5],
                "Total intl calls": [5, 4],
                "Total eve minutes": [200.0, 180.5],
                "Number vmail messages": [0, 5],
                "Voice mail plan": ["no", "yes"],
            }
        )
        y_train = np.array([0, 1])

        # Encode categorical columns
        le_international = LabelEncoder()
        le_voice = LabelEncoder()
        X_train["International plan"] = le_international.fit_transform(
            X_train["International plan"]
        )
        X_train["Voice mail plan"] = le_voice.fit_transform(X_train["Voice mail plan"])

        return X_train, y_train

    def test_prepare_data(self, sample_data):
        """Test if prepare_data function runs without errors and returns valid splits."""
        train_path, test_path = sample_data
        X_train, X_test, y_train, y_test = prepare_data(train_path, test_path)

        assert X_train is not None, "X_train should not be None"
        assert X_test is not None, "X_test should not be None"
        assert y_train is not None, "y_train should not be None"
        assert y_test is not None, "y_test should not be None"
        assert len(X_train) == 2, "X_train should have 2 rows"
        assert len(X_test) == 2, "X_test should have 2 rows"
        assert len(y_train) == 2, "y_train should have 2 rows"
        assert len(y_test) == 2, "y_test should have 2 rows"

    def test_model_evaluation(self, sample_train_data):
        """Test if model evaluation returns a valid accuracy score."""
        X_train, y_train = sample_train_data
        model = RandomForestClassifier(random_state=42).fit(X_train, y_train)
        metrics = evaluate_model(model, X_train, y_train)

        assert isinstance(metrics, dict), "Metrics should be a dictionary"
        assert "accuracy" in metrics, "Accuracy should be in metrics"
        assert 0.0 <= metrics["accuracy"] <= 1.0, "Accuracy should be between 0 and 1"

    def test_train_model_returns_model(self, sample_train_data):
        """Test if train_model returns an XGBClassifier."""
        X_train, y_train = sample_train_data
        model = train_model(X_train, y_train, model_version="test_1.0")

        assert isinstance(model, xgb.XGBClassifier), "Model should be an XGBClassifier"
        assert model is not None, "Model should not be None"

    def test_evaluate_model_metrics(self, sample_train_data):
        """Test if evaluate_model returns a metrics dictionary."""
        X_train, y_train = sample_train_data
        model = train_model(X_train, y_train, model_version="test_1.0")
        metrics = evaluate_model(model, X_train, y_train)

        assert isinstance(metrics, dict), "Metrics should be a dictionary"
        assert "accuracy" in metrics, "Accuracy should be in metrics"
        assert "roc_auc" in metrics, "ROC AUC should be in metrics"
        assert "log_loss" in metrics, "Log loss should be in metrics"
        assert 0.0 <= metrics["accuracy"] <= 1.0, "Accuracy should be between 0 and 1"
        assert 0.0 <= metrics["roc_auc"] <= 1.0, "ROC AUC should be between 0 and 1"
