pipeline {
  agent { label 'ai-lab' }
  stages {
    stage('Checkout') { steps { checkout scm } }
    stage('Student pipeline') {
      steps { error('Add install, automated tests, reporting, IaC validation, image build and smoke test stages') }
    }
  }
}
