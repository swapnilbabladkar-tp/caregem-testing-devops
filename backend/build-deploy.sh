#!/bin/bash

start=$(date +%s)

# Get the current commit hash
current_commit=$1

# Get the previous commit hash
previous_commit=$2

# Get the list of changed files between the two commits
changed_files=$(git diff --name-only $previous_commit $current_commit)

# Filter the names of services which are changed
changed_services=$(echo "$changed_files" | sed 's/backend\///g' | sed 's/\/.*//g')

# Split the list of changed files into an array
changed_files_array=$(echo $changed_services | awk '{gsub(/[ \t]+/, ","); print}')
IFS=',' read -ra changed_files_list <<< "$changed_files_array"

# Unique entries of services 
changed_service_list=($(echo "${changed_files_list[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

echo $changed_service_list
: ' if echo "${changed_service_list[@]}" | grep -q "layers"; then
    echo "BUILDING ALL SERVICES"
    echo
    for service_name in *-trigger *-service; do

        # Template file 
        buildfile=${service_name}/${service_name}.yaml

        # Deploy all functions one-by-one
        echo "----------------------------------------------------"
        echo "| Status - Building | Function - $function_name "
        echo "----------------------------------------------------"
        sam build -t ./$buildfile --parallel
        echo "-----------------------------------------------------------"
        echo "| Status - Build Completed | Function - $function_name "
        echo "-----------------------------------------------------------"

        # Template file
        deployfile=${service_name}/${service_name}-config.toml

        # Deploy all functions one-by-one
        echo "----------------------------------------------------"
        echo "| Status - Deploying | Function - $function_name "
        echo "----------------------------------------------------"
        sam deploy \
        --config-file $deployfile \
        --stack-name $service_name \
        --s3-bucket $SAM_CLI_SOURCE_BUCKET \
        --no-confirm-changeset --no-fail-on-empty-changeset
        echo "--------------------------------------------------------------"
        echo "| Status - Deployment Completed| Function - $function_name "
        echo "---------------------------------------------------------------" 
    done
    exit
elif echo "${changed_service_list[@]}" | egrep -q "service|trigger"; then
    echo "BUILDING ONLY CHANGED SERVICES"
    echo
    # Loop through the list of changed files
    for file in "${changed_service_list[@]}"; do
        echo $file 
        if echo $file | egrep -q "migration|iac|scripts|bin|aws_scripts"; then
            echo "----------------------------------------------------"
            echo "Build not applicable for service $file"
            echo "----------------------------------------------------"
        else
            function_name=$(echo $file | cut -d '/' -f 2)
            
            # Template file
            buildfile=${function_name}/${function_name}.yaml

            # Build the function which is changed
            echo "----------------------------------------------------"
            echo "| Status - Building | Function - $function_name "
            echo "----------------------------------------------------"
            sam build -t $buildfile --parallel
            echo "-----------------------------------------------------------"
            echo "| Status - Build Completed | Function - $function_name "
            echo "-----------------------------------------------------------"

            # Template file 
            deployfile=${function_name}/${function_name}-config.toml

            # Deploy the function which is changed
            echo "----------------------------------------------------"
            echo "| Status - Deploying | Function - $function_name "
            echo "----------------------------------------------------" 
            sam deploy \
            --config-file $deployfile \
            --stack-name $function_name \
            --s3-bucket $SAM_CLI_SOURCE_BUCKET \
            --no-confirm-changeset --no-fail-on-empty-changeset
            echo "--------------------------------------------------------------"
            echo "| Status - Deployment Completed| Function - $function_name "
            echo "---------------------------------------------------------------"
        fi
    done
else
    echo ${changed_service_list[@]}
    echo "NO BACKENDSERVICE MODIFIED"    
fi

echo "Cleaning up build artifacts for $service_name ..."
rm -r ./.aws-sam
echo "Clean up completed" '

end=$(date +%s)
echo "-----------------------------------------------------------"
echo "Elapsed Time: $(($end-$start)) seconds"
echo "-----------------------------------------------------------"
